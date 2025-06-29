import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient
import google.generativeai as genai
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Initialize MongoDB Client ---
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    collection = db[MONGO_COLLECTION_NAME]
    # Verify connection
    client.admin.command('ping')
    print("MongoDB connection successful.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    exit()

# --- Initialize Gemini AI ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    embedding_model = 'models/embedding-001'
    print(f"Gemini AI configured with model: {embedding_model}")
except Exception as e:
    print(f"Error configuring Gemini AI: {e}")
    exit()

def create_composite_text_for_embedding(record: dict) -> str:
    """
    Creates a single string from the displayName, description, and slots
    of a record for generating an embedding.
    """
    intent = record.get("intent", {})
    display_name = intent.get("displayName", "")
    description = intent.get("description", "")
    
    # Convert the slots list of dictionaries to a JSON string for a consistent representation
    slots = intent.get("slots", [])
    slots_text = json.dumps(slots, separators=(',', ':'))
    
    # Combine all text fields into a single string
    combined_text = f"displayName: {display_name} description: {description} slots: {slots_text}"
    
    return combined_text.strip()

def process_and_update_records():
    """
    Fetches all records, generates embeddings, and updates them in MongoDB.
    """
    print("\n--- Starting to process and update records ---")
    
    try:
        all_records = list(collection.find({}))
        if not all_records:
            print("No records found in the collection to process.")
            return

        print(f"Found {len(all_records)} records to process.")

        for record in all_records:
            record_id = record['_id']
            try:
                # Create the composite text for embedding
                text_to_embed = create_composite_text_for_embedding(record)
                
                # Generate the embedding
                embedding_response = genai.embed_content(
                    model=embedding_model,
                    content=text_to_embed,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                
                vector_embedding = embedding_response['embedding']

                # Update the record in MongoDB
                collection.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "vector_embedding": vector_embedding,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                print(f"Successfully updated record {record_id}")

            except Exception as e:
                print(f"An error occurred while processing record {record_id}: {e}")

    except Exception as e:
        print(f"An error occurred while fetching records: {e}")

    print("\n--- Finished processing records ---")


if __name__ == "__main__":
    # This block will run when the script is executed directly.
    # It will process all existing records in the collection.
    process_and_update_records()