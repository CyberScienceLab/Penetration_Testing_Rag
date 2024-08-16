
# ========================================================================
TABLE_NAME = 'exploits'
BATCH_SIZE = 100
# ========================================================================

class Exploit:
    
    def __init__(self, id: int, file_path: str, description: str, published: int, 
                 author: str, exploit_type: str, platform: str, codes: list[str]):
        self.id = id
        self.file_path = file_path
        self.description = description
        self.published = published
        self.author = author
        self.exploit_type = exploit_type
        self.platform = platform
        self.codes = codes

    
    def __str__(self) -> str:
        pass


# create table if doesn't already exist
def create_table():
    pass


# insert a list of values, if a value already exists do nothing
# use batches to prevent overloading db
def insert(values: list[tuple]):
    pass


# search for rows in db by specified fields
# return a list of Exploit with a length of 'limit'
def search_db(id: int, file_path: str, description: str, published: int, author: str, 
              exploit_type: str, platform: str, codes: list[str], limit: int) -> list[Exploit]:
    pass
