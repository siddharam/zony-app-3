import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
from dotenv import load_dotenv
import google.generativeai as genai
import json
import uuid
import logging
from datetime import datetime

# --- Logging Setup ---
# This will create a log file to store all Gemini interactions.
logging.basicConfig(
    filename='gemini_interactions.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "intent_assistant_db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_GEN_MODEL = os.getenv("GEMINI_GEN_MODEL", "gemini-1.5-flash") # Load model from env
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/embedding-001") # Added for embeddings

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Database Setup ---
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    threads_collection = db["chat_threads"]
    intents_collection = db["intents"]
    client.server_info()
    print("MongoDB connection successful.")
    # Log the database and collection names
    print(f"Using database: '{MONGO_DB_NAME}'")
    print(f"Using collections: '{threads_collection.name}', '{intents_collection.name}'")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    exit()

# --- Gemini Model Configuration ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_GEN_MODEL) # Use the model from env
    print("Gemini model configured successfully.")
    print(f"Using Gemini model: '{GEMINI_GEN_MODEL}'")
    print(f"Using Gemini embedding model: '{GEMINI_EMBEDDING_MODEL}'")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    exit()

# --- Prompt Engineering Functions ---

def get_dynamic_intent_schema_prompt(conversation_text):
    """
    Creates a prompt for the LLM to dynamically generate an intent schema from a conversation.
    """
    prompt = f"""
    Act as a "Master Intent Architect". Your primary job is to analyze a user's request and create a detailed, structured schema for it. This schema is the plan for a conversation.

    Conversation History:
    {conversation_text}

    Based on the user's goal, generate a single, valid JSON object that defines the intent schema.
    The JSON object must have this structure:
    {{
      "intentName": "PascalCaseName_v1",
      "displayName": "User-Friendly Name",
      "description": "A user-centric summary of the goal. Start with 'User wants to...' or 'User is looking for...'.",
      "slots": [
        {{ "name": "camelCaseSlotName", "type": "string|number|enum", "required": true|false, "options": ["option1"] (if type is 'enum') }}
      ]
    }}

    **CRITICAL RULES:**
    1.  **Be Thorough:** For any real-world task (e.g., finding a tutor, selling an item, booking a trip), you MUST define at least two `required` slots. Do not create trivial schemas. Think about what information is absolutely essential for the task.
    2.  **No Goal, No Schema:** If the conversation is a simple greeting (e.g., "hi", "hello") or has no clear actionable goal, respond with the exact string "UNCLEAR".
    3.  **JSON or UNCLEAR only:** Your response must be ONLY the JSON object or the word "UNCLEAR". Do not add any other text, explanations, or formatting.
    """
    return prompt

def get_slot_extraction_prompt(conversation_text, dynamic_schema):
    """
    Creates a prompt to extract ALL data for slots based on the full conversation history.
    This is used to both update the state and for the final extraction.
    """
    slot_details = "\n".join([f"- {s['name']} ({s['type']})" for s in dynamic_schema['slots']])
    prompt = f"""
    Analyze the entire conversation. The user's goal is '{dynamic_schema['displayName']}'.
    Extract the values for the following slots from the conversation.

    Slots to extract:
    {slot_details}

    Conversation:
    {conversation_text}

    Respond with a single, valid JSON object containing only the "filledSlots" key.
    Example: {{ "filledSlots": {{ "slotName1": "value1", "slotName2": 123 }} }}
    - Ensure data types match the slot definitions.
    - If you cannot extract a value for a slot, omit it from the JSON.
    - Your response must ONLY be the JSON object. If no slots can be filled, return an empty filledSlots object.
    """
    return prompt

def get_guided_conversational_prompt(conversation_text, dynamic_schema, filled_slots, user_id):
    """
    Guides the LLM to ask the next logical question to fill the *next* missing required or optional slot.
    """
    schema_json_string = json.dumps(dynamic_schema)
    filled_slots_json_string = json.dumps(filled_slots)

    prompt = f"""
    You are an empathetic, friendly, and helpful AI assistant. Your tone should be helpful and understanding. You are speaking with a user named '{user_id}'.

    Your main goal is to help {user_id} complete a task by filling out a form based on this JSON schema:
    {schema_json_string}

    This is the information you have confirmed so far:
    {filled_slots_json_string}

    This is the full conversation history:
    {conversation_text}

    Your task is to determine the most logical next question to ask to continue filling the form.

    Instructions:
    1.  **Prioritize Required Information:** First, check if any 'required' slots from the schema are missing from the conversation. If so, ask a friendly question for the very next missing *required* slot.
    2.  **Continue with Optional Information:** If all 'required' slots are filled, check for any 'optional' (required: false) slots that are missing. If there are any, ask a friendly question for the next single *optional* slot.
    3.  **Signal Completion:** Only when all slots (both required and optional) have been filled, or if the user indicates they don't want to provide more optional details, respond with the exact machine-readable string "ALL_SLOTS_FILLED".
    4.  **One Question at a Time:** Do not ask for more than one piece of information at a time.
    5.  **Personalize:** Address the user, {user_id}, by their name when it feels natural.
    6.  **Your response must ONLY be the AI's conversational question or the "ALL_SLOTS_FILLED" string.**
    """
    return prompt

def get_confirmation_prompt(filled_slots, user_id, dynamic_schema):
    """
    Creates a prompt for the AI to summarize the collected data and ask for confirmation.
    """
    user_goal = dynamic_schema.get('description', 'your request')
    details = "\n".join([f"- {key.replace('camelCase', '').title()}: {value}" for key, value in filled_slots.items()])
    prompt = f"""
    You are an AI assistant. Your task is to summarize the details you've collected from the user, {user_id}, and ask for their confirmation before proceeding.

    First, state the user's main goal, which is: "{user_goal}".
    Then, list the details you have collected.

    Here are the details:
    {details}

    Generate a friendly, conversational summary that includes the user's goal and the details. Then ask {user_id} if this information is correct or if they'd like to make any changes.
    Example: "Okay {user_id}, let's confirm. It looks like your goal is to '{user_goal}'. Based on our chat, here are the details I have:
    {details}
    Is that all correct?"
    """
    return prompt

def get_confirmation_analysis_prompt(user_message):
    """
    Analyzes the user's response to the confirmation question.
    """
    prompt = f"""
    Analyze the user's latest message to see if they are confirming the details you just summarized.

    User's message: "{user_message}"

    - If the user's message is a confirmation (e.g., "yes", "that's correct", "looks good", "go ahead"), respond with the single word: CONFIRMED
    - If the user's message indicates a correction or change (e.g., "no, the year is 2022", "actually, I want..."), respond with the single word: CORRECTION
    - If the user's response is unclear, assume it's a CORRECTION.
    """
    return prompt

def get_correction_prompt(conversation_text, user_id):
    """
    Creates a prompt for the AI to ask for corrections after a user denies a summary.
    """
    prompt = f"""
    You are an empathetic AI assistant talking to {user_id}.
    You just summarized the user's request, but they have indicated that something is incorrect.
    Your task is to ask a friendly, open-ended question to understand what needs to be changed. Look at the last thing the user said to see if they already specified the correction.

    Full Conversation History:
    {conversation_text}

    Generate a natural response.
    Example 1: "My apologies, {user_id}. Could you please tell me what I need to change?"
    Example 2: "No problem at all. What should I correct for you?"
    """
    return prompt


# --- Helper Function for a single point of interaction with Gemini ---
def generate_gemini_content(user_id, thread_id, prompt_text):
    """A centralized function to call the Gemini API and log the interaction."""
    try:
        log_prompt = json.dumps(prompt_text) if isinstance(prompt_text, list) else prompt_text
        logging.info(f"USER_ID: {user_id} | THREAD_ID: {thread_id} | PROMPT: {log_prompt}")

        response = model.generate_content(prompt_text)
        response_text = response.text.strip()

        logging.info(f"USER_ID: {user_id} | THREAD_ID: {thread_id} | RESPONSE: {response_text}")
        return response_text
    except Exception as e:
        logging.error(f"USER_ID: {user_id} | THREAD_ID: {thread_id} | Gemini API Error: {e}")
        return None # Return None on error

# --- API Endpoints ---

@app.route('/intents', methods=['GET'])
def get_intents():
    """Fetches all completed intents from the database."""
    try:
        all_intents = list(intents_collection.find({}, {'_id': 0, 'intent.filledSlots': 1, 'intent.displayName': 1, 'intent.description': 1, 'userId': 1, 'intentId': 1, 'createdAt': 1}))
        return jsonify(all_intents), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/intents/<string:userId>', methods=['GET'])
def get_user_intents(userId):
    """Fetches all completed intents for a specific user."""
    try:
        user_intents = list(intents_collection.find({"userId": userId}, {'_id': 0}))
        return jsonify(user_intents), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/chat', methods=['POST'])
def handle_chat():
    """
    Handles chat messages, orchestrates dynamic intent schema generation and slot filling.
    """
    data = request.json
    user_id = data.get('userId')
    thread_id = data.get('threadId')
    message_content = data.get('message')

    if not all([user_id, thread_id, message_content]):
        return jsonify({"error": "Missing required fields"}), 400

    thread = threads_collection.find_one_and_update(
        {"threadId": thread_id, "userId": user_id},
        {"$setOnInsert": {"threadId": thread_id, "userId": user_id, "messages": [], "dynamic_schema": None, "filled_slots": {}, "status": "GATHERING"}},
        upsert=True,
        return_document=True
    )

    thread['messages'].append({"role": "user", "content": message_content})
    conversation_history = thread['messages']
    conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])

    dynamic_schema = thread.get('dynamic_schema')
    thread_status = thread.get('status', 'GATHERING')
    ai_response_content = ""

    try:
        if thread_status == "COMPLETED":
            ai_response_content = "It looks like we've already finalized your request. If you'd like to start a new one, just let me know!"
        elif thread_status == "AWAITING_CONFIRMATION":
            analysis_prompt = get_confirmation_analysis_prompt(message_content)
            user_decision = generate_gemini_content(user_id, thread_id, analysis_prompt)

            if user_decision == "CONFIRMED":
                filled_slots = thread.get('filled_slots', {})

                # Convert slot values to sentence case
                for key, value in filled_slots.items():
                    if isinstance(value, str):
                        filled_slots[key] = value.capitalize()
                
                final_intent_data = {"filledSlots": filled_slots}
                if not intents_collection.find_one({"threadId": thread_id}):
                    new_intent = {
                        "intentId": str(uuid.uuid4()),
                        "threadId": thread_id,
                        "userId": user_id,
                        "createdAt": datetime.utcnow(),  # Added timestamp
                        "intent": {**dynamic_schema, **final_intent_data},
                        "vector_embedding": None # Initialize with None
                    }

                    # Generate and add vector embedding
                    try:
                        display_name = dynamic_schema.get('displayName', '')
                        description = dynamic_schema.get('description', '')
                        slots_text = json.dumps(dynamic_schema.get('slots', {}))
                        embedding_text = f"Display Name: {display_name}\nDescription: {description}\nSlots: {slots_text}"
                        
                        embedding_response = genai.embed_content(
                            model=GEMINI_EMBEDDING_MODEL,
                            content=embedding_text,
                            task_type="RETRIEVAL_DOCUMENT"
                        )
                        new_intent['vector_embedding'] = embedding_response['embedding']
                    except Exception as e:
                        logging.error(f"Could not generate embedding for thread {thread_id}: {e}")

                    result = intents_collection.insert_one(new_intent)
                    print(f"Intent for thread {thread_id} inserted with ID: {result.inserted_id}")
                    
                    # --- FIX START ---
                    # Prepare the intent for JSON serialization before emitting
                    new_intent.pop('_id') # Remove the BSON ObjectId
                    if isinstance(new_intent.get('createdAt'), datetime):
                        new_intent['createdAt'] = new_intent['createdAt'].isoformat() # Convert datetime to string
                    # --- FIX END ---
                    
                    socketio.emit('new_intent', new_intent)

                ai_response_content = "Perfect! I've posted your request on your behalf."
                threads_collection.update_one({"threadId": thread_id}, {"$set": {"status": "COMPLETED"}})
            else: # CORRECTION
                threads_collection.update_one(
                    {"threadId": thread_id},
                    {"$set": {"status": "GATHERING", "dynamic_schema": None, "filled_slots": {}}}
                )
                dynamic_schema = None
                ai_response_content = "Understood. Thanks for the correction. Let me re-evaluate based on your changes. One moment..."

        # This block now runs for GATHERING status, or if a CORRECTION reset the schema
        if thread_status == "GATHERING":
            if not dynamic_schema:
                prompt = get_dynamic_intent_schema_prompt(conversation_text)
                cleaned_response_text = generate_gemini_content(user_id, thread_id, prompt)
                if cleaned_response_text and cleaned_response_text != "UNCLEAR":
                    try:
                        dynamic_schema = json.loads(cleaned_response_text.replace("```json", "").replace("```", ""))
                        threads_collection.update_one({"threadId": thread_id}, {"$set": {"dynamic_schema": dynamic_schema}})
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"Could not parse dynamic schema: {e}. Response: '{cleaned_response_text}'")

            if dynamic_schema:
                required_slots_exist = any(s.get('required', False) for s in dynamic_schema.get('slots', []))
                if not required_slots_exist:
                    ai_response_content = "That's an interesting request. To make sure I understand correctly, could you tell me a bit more about what you'd like to accomplish?"
                else:
                    update_slots_prompt = get_slot_extraction_prompt(conversation_text, dynamic_schema)
                    update_cleaned_text = generate_gemini_content(user_id, thread_id, update_slots_prompt)
                    filled_slots = {}
                    if update_cleaned_text:
                        try:
                            updated_data = json.loads(update_cleaned_text.replace("```json", "").replace("```", ""))
                            if 'filledSlots' in updated_data:
                                filled_slots = updated_data['filledSlots']
                                threads_collection.update_one({"threadId": thread_id}, {"$set": {"filled_slots": filled_slots}})
                        except (json.JSONDecodeError, KeyError): pass

                    prompt = get_guided_conversational_prompt(conversation_text, dynamic_schema, filled_slots, user_id)
                    next_step_response = generate_gemini_content(user_id, thread_id, prompt)

                    if next_step_response and "ALL_SLOTS_FILLED" in next_step_response:
                        threads_collection.update_one({"threadId": thread_id}, {"$set": {"status": "AWAITING_CONFIRMATION"}})
                        confirmation_prompt = get_confirmation_prompt(filled_slots, user_id, dynamic_schema)
                        ai_response_content = generate_gemini_content(user_id, thread_id, confirmation_prompt)
                    else:
                        ai_response_content = next_step_response

            else: # Still no schema after trying
                ai_response_content = generate_gemini_content(user_id, thread_id, [{"role": m["role"], "parts": [m["content"]]} for m in conversation_history])

    except Exception as e:
        print(f"Error during conversational response generation: {e}")
        logging.error(f"Error in handle_chat for thread {thread_id}: {e}") # Added logging
        return jsonify({"error": "Failed to get AI response"}), 500

    if not ai_response_content:
        ai_response_content = "I'm sorry, I'm having trouble processing that request. Could you try rephrasing?"

    thread['messages'].append({"role": "model", "content": ai_response_content})
    threads_collection.update_one({"threadId": thread_id}, {"$set": {"messages": thread['messages']}})

    return jsonify({"reply": ai_response_content})

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")

# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Flask-SocketIO server on port 5001...")
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)