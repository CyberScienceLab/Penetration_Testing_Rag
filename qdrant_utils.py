from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import VectorParams
from langchain_qdrant import QdrantVectorStore
import time

# ========================================================================
QDRANT_URL = 'http://localhost:6333'
VECTOR_SIZE = 1024
BATCH_SIZE = 100
EMBEDDING_DELAY_SECONDS = 5
# ========================================================================

# TODO: create a single instance of this to be shared with all other rags
embeddings = HuggingFaceBgeEmbeddings(
    model_name="BAAI/bge-large-en",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)


# create collection if it doesn't already exist
def create_collections(collections: list[str]):
    client = QdrantClient(
        url=QDRANT_URL, prefer_grpc=False
    )
        
    for collection in collections:
        try:
            qd_collections = client.get_collections()
            if any(qd_collection.name == collection for qd_collection in qd_collections.collections):
                print(f'[QDRANT] Collection {collection} already exists')
            
            else:
                client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance='Cosine'),
                )
                print(f"[QDRANT] Successfully creating collection: {collection}")

        except Exception as e:
            print(f"[ERROR] Error creating during creation collection: {collection}\n {e}")

    client.close()


# load embeddings into collection with custom metadata
# use batches to prevent file descriptor error
def load_embeddings_custom_metadata(texts: list[str], metadata: list[dict], collection: str):
    client = QdrantClient(
        url=QDRANT_URL, prefer_grpc=False
    )
    
    text_embeddings = embeddings.embed_documents(texts)
    print(f'[QDRANT] Vector embeddings created')

    # length of texts and metadata should always be the same, but incase
    min_size = min(len(texts), len(metadata))
    for i in range(0, min_size, BATCH_SIZE):
        batch_texts = texts[i:i + BATCH_SIZE]
        batch_metadata = metadata[i:i + BATCH_SIZE]
        batch_embeddings = text_embeddings[i:i + BATCH_SIZE]


        client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    # TODO: remove the + 50000
                    id=batch_metadata[n].get('id', i * BATCH_SIZE + n) + 50000,
                    vector=embedding,
                    payload={
                        'metadata': batch_metadata[n],
                        'page_content': batch_texts[n]
                    }
                )
                for n, embedding in enumerate(batch_embeddings)
            ]
        )

        print(f'[QDRANT] Batch {min(i + BATCH_SIZE, min_size)} of {min_size}')
        time.sleep(EMBEDDING_DELAY_SECONDS)


    client.close()
    print("[QDRANT] Embeddings successfully loaded into collection")


# execute a similarity search with the given query 
# return the id of the top num_matches matches
def retrieve_relevant_context_ids(query: str, num_matches: int, collection: str) -> list[int]:
    client = QdrantClient(
        url=QDRANT_URL, prefer_grpc=False
    )

    vector_store = QdrantVectorStore(client=client, embedding=embeddings, collection_name=collection)
    points = vector_store.similarity_search_with_score(query=query, k=num_matches)

    content = []
    for point in points:
        body, _ = point # ignore vectors

        if 'id' in body.metadata:
            content.append(body.metadata['id'])

    client.close()
    print(f'[QDRANT] Retrieved {len(content)} points of exploit data')
    return content
