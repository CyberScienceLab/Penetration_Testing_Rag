import postgres_utils as pg
import qdrant_utils as qd

class Pen_Test_Rag:

    def __init__(self, tokenizer, model):
        self.tokenizer = tokenizer
        self.model = model


    # create qdrant collection and postgres table
    def init_database(self):
        pass


    # load data from a csv to qdrant and postgres
    def load_data_from_csv(self, file_path: str):
        pass


    # used by RAG_App, don't change function signature
    # return: [{system message}, {user message}], [list of relevant context chunks]
    def get_messages_with_context(self, prompt: str, extra_context: str, num_chunks: int) -> tuple[list[dict[str, str]], list[str]]:
        pass


if __name__ == '__main__':
    print('Penetration Testing RAG')
