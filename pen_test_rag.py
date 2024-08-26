from prompts import SYSTEM_TEXT_CLASSIFICATION_PROMPT, SYSTEM_MAIN_PROMPT
import postgres_utils as pg
import qdrant_utils as qd

import csv
import fitz

# ========================================================================
DESCRIPTION_INDEX = 2
ID_INDEX = 0
FILE_STR_MAX_CHARS = 3000
MAX_SNIPPET_LEN = 1000
EXPLOITS_COLLECTION = 'exploits'
EXPLOITS_CODE_COLLECTION = 'exploits-code'
# ========================================================================


class Pen_Test_Rag:

    def __init__(self, tokenizer, model):
        self.tokenizer = tokenizer
        self.model = model


    # create qdrant collection and postgres table
    def init_database(self):
        pg.create_table()
        qd.create_collections([EXPLOITS_COLLECTION, EXPLOITS_CODE_COLLECTION])


    # load data from a csv to qdrant and postgres
    # TODO: add flag here that can be a user prompt to ask if user wants to
    #       load both cuz sometimes they might just want one like if qdrant breaks again
    def load_data_from_csv(self, file_path: str, embed_files: bool):
        pg_data = []
        descriptions = []
        metadata = []

        folder_path = '/'.join(file_path.split('/')[:-1]) + '/'

        try:
            with open(file=file_path, mode='r', newline='') as f:
                csv_reader = csv.reader(f)
                _ = next(csv_reader) # skip header

                for i, row in enumerate(csv_reader):
                    try:
                        id = int(row[0]) # INTEGER
                        file = folder_path + row[1] # TEXT
                        description = row[2].lower() # TEXT
                        published = int(row[3][:4]) # INTEGER (year)
                        author = row[4].lower() # TEXT
                        e_type = row[5].lower() # TEXT (exploit type)
                        platform = row[6].lower() # TEXT
                        codes = [code.lower() for code in row[11].split(';') if code] # TEXT[]

                    except Exception as e:
                        print(f'[ERROR] Error occurred while reading CSV, Skipping row {i + 2}.')
                        continue

                    
                    pg_data.append((id, file, description, published, author, e_type, platform, codes))
                    descriptions.append(description)
                    metadata.append({'id': id})

                    if embed_files:
                        self.embed_code(file, id)


            pg.insert(pg_data)
            qd.load_embeddings_custom_metadata(descriptions, metadata, EXPLOITS_COLLECTION)

        except Exception as e:
            print(f'[ERROR] Error reading from file {file_path}: {e}')


    # embed file code into qdrant exploit-code collection
    def embed_code(self, file_path: str, id: int):
        file_str = self.retrieve_file_as_str(file_path)

        if len(file_str) > 0:
            file_arr = [file_str[i:i + MAX_SNIPPET_LEN] for i in range(0, len(file_str), MAX_SNIPPET_LEN)]
            qd.load_embeddings_custom_metadata(file_arr, [{'id': id} for _ in file_arr], EXPLOITS_CODE_COLLECTION)


    # used by RAG_App, don't change function signature
    # return: [{system message}, {user message}], [list of relevant context chunks]
    def get_messages_with_context(self, prompt: str, file_text: str, num_chunks: int) -> tuple[list[dict[str, str]], list[str]]:
        prompt = prompt.lower()

        relevant_context = []
        if len(file_text) == 0: # no file passed
            classification_res = self.classify_text(prompt)
            print(classification_res)
            classified_obj = self.build_classified_obj(classification_res)

            if classified_obj.get('type', '') != 'Structured':
                # if empty object back do vector search with original query
                classified_obj['fields'] = self.retrieve_ids_formatted(
                    classified_obj.get('query', prompt), 
                    num_chunks
                )

            relevant_context = pg.search_db(classified_obj['fields'], num_chunks)

            # if no results back from structured search, do similarity search
            # and then search postgres again with resulting ids
            if len(relevant_context) == 0:
                classified_obj['fields'] = self.retrieve_ids_formatted(
                    prompt,
                    num_chunks
                )

                relevant_context = pg.search_db(classified_obj['fields'], num_chunks)


        else: # match file code
            relevant_ids = qd.retrieve_relevant_context_ids(file_text, num_chunks, EXPLOITS_CODE_COLLECTION)
            relevant_context = pg.search_db({'ids': relevant_ids}, num_chunks)


        for i in range(len(relevant_context)):

            # if someone is providing the file then no need to give it back in response 
            if len(file_text) == 0:
                relevant_context[i].file_snippet = (
                    '[START CODE SNIPPET]' + 
                    self.retrieve_file_as_str(relevant_context[i].file_path) + 
                    '[END CODE SNIPPET]'
                )

            relevant_context[i].file_path = self.convert_file_path_to_gh_url(
                relevant_context[i].file_path
            )


        return (
            self.build_messages(prompt, file_text, relevant_context), 
            # must do str(context) to ensure __str__ is getting called
            [str(context) for context in relevant_context]
        )
    

    # take local file path for the exploit and change it to the github
    # url for the exploit in exploit db repository
    def convert_file_path_to_gh_url(self, file_path: str) -> str:
        blob = '/-/blob/main/'
        prefix = 'https://gitlab.com/exploit-database/'

        _, folder, *file_path = file_path.split('/')

        return prefix + folder + blob + '/'.join(file_path)


    # retrieve ids from qdrant formatted in a dict to be stored in classified_obj['fields']
    def retrieve_ids_formatted(self, query: str, num_matches: int):
        return { 'ids': qd.retrieve_relevant_context_ids(
            query, 
            num_matches,
            EXPLOITS_COLLECTION
        ) }


    # take file_path string which is retrieved from pg database, find file
    # return file contents as a string
    def retrieve_file_as_str(self, file_path: str) -> str:
        # TODO: move this to env probably, only required since RAG_App is in different location
        file_path = '/home/researchuser/mark/Penetration_Testing_Rag/' + file_path

        try:
            file_str = ''
            if file_path.lower().endswith('.pdf'):
                pdf_reader = fitz.open(file_path)
                pdf_str = ''
                for page_num in range(len(pdf_reader)):
                    page = pdf_reader.load_page(page_num)
                    pdf_str += page.get_text('text')
                    
                    if len(pdf_str) > FILE_STR_MAX_CHARS:
                        break

                file_str = pdf_str

            else:
                with open(file_path, mode='r', newline='') as f:
                    file_str = f.read(FILE_STR_MAX_CHARS)

            return file_str
            

        except Exception as e:
            print(f'[ERROR] Could not read file at path {file_path}: {e}')
            return ''
            

    # build messages array to be used by LLM with user prompt and relevant_context and file
    # return: [{'role': 'system', 'content': str}, {'role': 'user', 'content': str}]
    def build_messages(self, prompt: str, file_text: str, relevant_context: list[any]) -> list[dict]:
        relevant_context_str = '\n'.join(str(context) for context in relevant_context)
        
        return [
            {
                'role': 'system',
                'content': SYSTEM_MAIN_PROMPT
            },
            {
                'role': 'user',
                'content': prompt + 'Given the information below' + '\n**Exploit Data: **' + relevant_context_str
                    # (
                    #     'File Given: {file_text}' 
                    #     if len(file_text) > 0 and file_text != 'No File / extra context given.' 
                    #     else ''
                    # )
            }
        ]


    # use llama to classify whether 'text' is structured and unstructured
    # if structured return comma separated fields we can use to search db
    # Structured: author: mark schmid, date: 2024
    # if unstructured return original text without filler words to 'hopefully' 
    #   improve similarity search results
    # Unstructured: prompt with filler words missing
    def classify_text(self, text: str) -> str:
        messages = [
            {'role': 'system', 'content': SYSTEM_TEXT_CLASSIFICATION_PROMPT},
            {'role': 'user', 'content': text}
        ]

        input_ids = self.tokenizer.apply_chat_template(
            messages, 
            add_generation_prompt=True, 
            return_tensors="pt"
        ).to(self.model.device)

        outputs = self.model.generate(
            input_ids, 
            max_new_tokens=700, 
            eos_token_id=self.tokenizer.eos_token_id, 
            do_sample=True, 
            temperature=0.2, 
            top_p=0.9
        )

        return self.tokenizer.decode(
            outputs[0][input_ids.shape[-1]:], 
            skip_special_tokens=True
        )
    

    # use classify_text response and build dict to store fields in proper structure
    # input: 'Structured: author: Mark Schmid, platform: Linux, date_published: 2020'  
    # output: { 
    #   'type': 'Structured', 
    #   'fields': {
    #         'author': 'Mark Schmid',
    #         'platform': 'Linux',
    #         'date_published': 2020
    #     }
    # }
    # input: 'Unstructured: exploit buffer overflow in a Linux environment'  
    # output: 
    # {  
    #     'type': 'Unstructured',    
    #     'query': 'exploit buffer overflow in a Linux environment'  
    # }
    def build_classified_obj(self, res: str) -> dict[str, any]:
        try:
            search_type, info = res.split(': ', 1)
        except ValueError as e:
            print('[WARNING] Invalid response from LLM, defaulting to Unstructured')
            return {}


        if search_type == 'Structured':
            fields_and_values = info.split(',')

            return {
                'type': 'Structured',
                'fields': {
                    key.strip().lower(): 
                    value.strip().lower() for key, value in (
                        pair.split(':') for pair in fields_and_values
                    )
                }
            }
        
        if search_type == 'Unstructured':
            return {
                'type': 'Unstructured',
                'query': info
            }
    
        print('[WARNING] Invalid response from LLM, defaulting to Unstructured')
        return {}
    

# main function can be used to load data
if __name__ == '__main__':
    tokenizer, model = None, None

    # ============================ REMOVE ==========================
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    torch.cuda.empty_cache()
    from transformers.utils import logging
    logging.set_verbosity_error()
    # initalize and return  llama3 tokenizer and model
    def initialize_model():
        model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        return tokenizer, model

    tokenizer, model = initialize_model()
    # ============================ REMOVE ==========================

    rag = Pen_Test_Rag(tokenizer, model)
    print('==================')
    print('== Pen Test Rag ==')
    print('==================')

    while True:
        selection = input('Would you like to load data from CSV (y or n): ')

        if selection in 'Yy':
            rag.init_database()

            file_path = input('CSV File Path: ')

            rag.load_data_from_csv(file_path, False)


        elif selection in 'Tt': 
            # print('No Testing Setup')

            # prompt = 'Find an exploit that targets aix systems by Author Mark Schaefer in 1998.',
            # prompt = 'Can you give me an example of a buffer overflow on a linux system?',
            # prompt = 'Give me an example of an exploit related to CVE-2009-3699',
            # prompt = 'Give me an example of an exploit related to SQL Injection',
            # prompt = 'Can you show me a code example of HTML injection',
            # prompt = 'Show me exploits by John Doe targeting Windows systems from 2021.'
            prompt = input('Prompt: ')
            messages, chunks, file_str = rag.get_messages_with_context(prompt, '', 5)
            print(f'MARK :: messages -> {messages}')

            print(f'MARK :: file_str -> {file_str}')


        else:
            break
