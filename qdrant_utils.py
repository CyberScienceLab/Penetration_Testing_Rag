
# ========================================================================
QDRANT_URL = 'http://localhost:6333'
COLLECTION_NAME = 'exploits'
VECTOR_SIZE = 1024
BATCH_SIZE = 100
EMBEDDING_DELAY_SECONDS = 5
# ========================================================================

# create collection if it doesn't already exist
def create_collection():
    pass


# load embeddings into collection with custom metadata
# use batches to prevent file descriptor error
def load_embeddings_custom_metadata(texts: list[str], metadata: list[dict]):
    pass


# execute a similarity search with the given query 
# return the id of the top num_matches matches
def retrieve_relevant_context(query: str, num_matches: int) -> list[int]:
    pass
