# TODO: move db connection creation out of functions, AWFUL way to do it!

import psycopg2 as psy
import os
import time

# ========================================================================
TABLE_NAME = 'exploits'
BATCH_SIZE = 1000
BATCH_DELAY_SECONDS = 3
TABLE_FIELDS = ['id', 'file_path', 'description', 'date_published', 'author', 
                'e_type', 'platform', 'codes']
CREATE_TABLE_QUERY = f'''
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY,
    file_path TEXT,
    description TEXT,
    date_published INTEGER,
    author TEXT,
    e_type TEXT,
    platform TEXT,
    codes TEXT[]
);
'''
INSERT_QUERY = f'''
INSERT INTO {TABLE_NAME} ({', '.join(TABLE_FIELDS)})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING;
'''
CONNECTION_PARAMS = {
    'host': 'localhost',
    'port': 5432,
    'database': 'postgres',
    'user': 'postgres',
    'password': os.getenv('POSTGRES_PASSWORD')
}
# ========================================================================


class Exploit:
    
    def __init__(self, id: int, file_path: str, description: str, published: int, 
                 author: str, exploit_type: str, platform: str, codes: list[str]):
        self.id = id
        self.file_path = file_path
        self.description = description
        self.date_published = published
        self.author = author
        self.exploit_type = exploit_type
        self.platform = platform
        self.codes = codes

    
    # TODO: do we need to print all the fields?
    def __str__(self) -> str:
        return (
                'EXPLOIT{ '
                f'id: {self.id}, ' 
                f'file_path: {self.file_path}, ' 
                f'description: {self.description}, ' 
                f'date_published: {self.date_published}, ' 
                f'author: {self.author}, ' 
                f'exploit_type: {self.exploit_type}, ' 
                f'platform: {self.platform}, ' 
                f'codes: {self.codes} '
                '}'
            )


# create table if doesn't already exist
def create_table():
    try:
        with psy.connect(**CONNECTION_PARAMS) as con:
            with con.cursor() as cursor:
                cursor.execute(CREATE_TABLE_QUERY)
                con.commit()

        print(f'[POSTGRES] Table {TABLE_NAME} successfully created')

    except Exception as e:
        print(f'[ERROR] Error occurred while creating table {TABLE_NAME}: {e}')


# insert a list of values, if a value already exists do nothing
# use batches to prevent overloading db
def insert(values: list[tuple]):
    try:
        with psy.connect(**CONNECTION_PARAMS) as con:
            with con.cursor() as cursor:
                
                values_size = len(values)
                for i in range(0, values_size, BATCH_SIZE):
                    cursor.executemany(INSERT_QUERY, values[i:i + BATCH_SIZE])
                    con.commit()

                    print(f'[POSTGRES] Batch {min(values_size, i + BATCH_SIZE)} of {values_size}')
                    time.sleep(BATCH_DELAY_SECONDS)

        print(f'[POSTGRES] Exploit data successfully loaded')

    except Exception as e:
        print(f'[ERROR] Error loading exploit data: {e}')


# search for rows in db by specified fields
# return a list of Exploit with a length of 'limit'
def search_db(fields: dict[str, any], limit: int) -> list[Exploit]:
    try:
        with psy.connect(**CONNECTION_PARAMS) as con:
            with con.cursor() as cursor:
                
                where_statement = ''
                if 'ids' in fields:
                    where_statement ='id = ANY(%s)'

                else:
                    where_statement = ' AND '.join(
                        f'{key} @> ARRAY[%s]' if key == 'codes' 
                        else f'{key} = %s' for key in fields
                    )

                    
                search_query = f'''
                                SELECT * FROM {TABLE_NAME} WHERE
                                {where_statement}
                                LIMIT %s;
                                '''

                cursor.execute(search_query, (
                    *([fields['ids']] if 'ids' in fields else list(fields.values())),
                    limit,
                ))
                results = cursor.fetchall()

        print(f'[POSTGRES] Successfully retrieved {len(results)} rows of exploit data')
        return [Exploit(*exploit) for exploit in results]

    except Exception as e:
        print(f'[ERROR] Error retrieving exploit data from {TABLE_NAME} table: {e}')
        return []
