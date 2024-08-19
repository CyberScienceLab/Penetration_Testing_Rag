from prompts import SYSTEM_TEXT_CLASSIFICATION_PROMPT, SYSTEM_MAIN_PROMPT
import postgres_utils as pg
import qdrant_utils as qd

import csv

# ========================================================================
DESCRIPTION_INDEX = 2
ID_INDEX = 0
# ========================================================================


class Pen_Test_Rag:

    def __init__(self, tokenizer, model):
        self.tokenizer = tokenizer
        self.model = model


    # create qdrant collection and postgres table
    def init_database(self):
        pg.create_table()
        qd.create_collection()


    # load data from a csv to qdrant and postgres
    # TODO: add flag here that can be a user prompt to ask if user wants to
    #       load both cuz sometimes they might just want one like if qdrant breaks again
    def load_data_from_csv(self, file_path: str):
        pg_data = []
        descriptions = []
        metadata = []

        with open(file=file_path, mode='r', newline='') as f:
            csv_reader = csv.reader(f)
            _ = next(csv_reader) # skip header

            for i, row in enumerate(csv_reader):
                try:
                    id = int(row[0]) # INTEGER
                    file = row[1] # TEXT
                    description = row[2] # TEXT
                    published = int(row[3][:4]) # INTEGER (year)
                    author = row[4] # TEXT
                    e_type = row[5] # TEXT (exploit type)
                    platform = row[6] # TEXT
                    codes = [code for code in row[11].split(';') if code] # TEXT[]

                except Exception as e:
                    print(f'[ERROR] Error occurred while reading CSV, Skipping row {i + 2}.')
                    continue

                pg_data.append((id, file, description, published, author, e_type, platform, codes))
                descriptions.append(description)
                metadata.append({'id': id})


        pg.insert(pg_data)
        qd.load_embeddings_custom_metadata(descriptions, metadata)


    # used by RAG_App, don't change function signature
    # return: [{system message}, {user message}], [list of relevant context chunks]
    def get_messages_with_context(self, prompt: str, file_text: str, num_chunks: int) -> tuple[list[dict[str, str]], list[str]]:
        classification_res = self.classify_text(prompt)

        classified_obj = self.build_classified_obj(classification_res)

        if classified_obj.get('type', '') != 'Structured':
            # if empty object back do vector search with original query
            exploit_ids = qd.retrieve_relevant_context_ids(
                classified_obj.get('query', prompt), 
                num_chunks
            )

            classified_obj['fields']['ids'] = exploit_ids


        relevant_context = pg.search_db(classified_obj['fields'], num_chunks)

        return self.build_messages(prompt, file_text, relevant_context), relevant_context


    # build messages array to be used by LLM with user prompt and relevant_context and file
    # return: [{'role': 'system', 'content': str}, {'role': 'user', 'content': str}]
    def build_messages(self, prompt: str, file_text: str, relevant_context: list[any]) -> list[dict]:
        relevant_context_str = '\n'.join(str(context) for context in relevant_context)
        
        # TODO: move system prompt to the prompts.py file to make it nicer
        return [
            {
                'role': 'system',
                'content': f'''
                            You are a chat bot. I'm going to ask you a question and use the relevant
                            context to generate a response.

                            Relevant Context:
                            {relevant_context_str}
                            '''
            },
            {
                'role': 'user',
                'content': prompt + 'File Given: {file_text}' if len(file_text) > 0 else ''
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
    # TODO: remove later, just for testing
    # initialization copied from rag.py ==========================
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from transformers.utils import logging
    logging.set_verbosity_error()
    import torch
    torch.cuda.empty_cache()

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
    # initialization copied from rag.py ==========================

    rag = Pen_Test_Rag(tokenizer, model)
    print('==================')
    print('== Pen Test Rag ==')
    print('==================')

    while True:
        selection = input('Would you like to load data from CSV (y or n): ')

        if selection in 'Yy':
            rag.init_database()

            file_path = input('CSV File Path: ')

            if rag.load_data_from_csv(file_path):
                print(f'Data loading complete from {file_path}')

            else:
                print(f'[ERROR] Could not load data from {file_path}')


        if selection in 'Tt': # testing
            # print('No Testing Setup.')

            prompt = input('Prompt: ')
            messages, context = rag.get_messages_with_context(prompt, '', 5)

            print('MARK :: ')
            print(messages, context)


        else:
            break
