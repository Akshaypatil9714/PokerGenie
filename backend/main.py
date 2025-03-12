from fastapi import FastAPI
from dotenv import load_dotenv
from firebase_utils import ( create_poker_room, add_player_to_room, update_rebuy, register_player, authenticate_player, settle_game, update_chip_count, get_rooms_for_player, 
                            get_room_details, get_regular_players, send_game_summary_message)
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import re
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from langchain_google_genai import GoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from firebase_admin import firestore
from typing import Optional


# Load environment variables from .env file
# Load environment variables from the correct directory
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path)

# Debugging: Print environment variable status
firebase_key_status = "Loaded" if os.getenv("FIREBASE_KEY_JSON") else "Not Found"
print(f"Firebase Key Status: {firebase_key_status}")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Check if the API key is loaded
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")
print(f"Gemini API Key loaded: {GEMINI_API_KEY[:5]}...")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dictionary to track active WebSocket connections
active_connections: Dict[str, List[WebSocket]] = {}

class RegisterPlayerRequest(BaseModel):
    user_id: str
    player_name: str
    password: str
    phone: int

@app.post("/register_player/")
async def register_player_endpoint(payload: RegisterPlayerRequest):
    return register_player(payload.user_id, payload.player_name, payload.password, payload.phone)

class AuthenticatePlayerRequest(BaseModel):
    user_id: str
    password: str

@app.post("/authenticate_player/")
async def authenticate_player_endpoint(payload: AuthenticatePlayerRequest):
    return authenticate_player(payload.user_id, payload.password)

class CreateRoomRequest(BaseModel):
    buy_in: int
    created_by: str
    rebuys: bool = False

@app.post("/create_room/")
async def create_room(payload: CreateRoomRequest):
    return create_poker_room(payload.buy_in, payload.created_by, payload.rebuys)

class AddPlayerRequest(BaseModel):
    room_id: str
    user_id: str
    buy_in: int

@app.post("/add_player/")
async def add_player(payload: AddPlayerRequest):
    return add_player_to_room(payload.room_id, payload.user_id, payload.buy_in)

class UpdateRebuyRequest(BaseModel):
    room_id: str
    user_id: str
    buy_in: int

@app.post("/update_rebuy/")
async def update_rebuy_endpoint(payload: UpdateRebuyRequest):
    return update_rebuy(payload.user_id, payload.room_id, payload.buy_in)

class UpdateChipCountRequest(BaseModel):
    room_id: str
    user_id: str
    chip_change: int

@app.post("/update_chip_count/")
async def update_chip_count_endpoint(payload: UpdateChipCountRequest):
    return update_chip_count(payload.user_id, payload.room_id, payload.chip_change)

class SettleGameRequest(BaseModel):
    room_id: str

@app.post("/settle_game/")
async def settle_game_endpoint(payload: SettleGameRequest):
    return settle_game(payload.room_id)

@app.get("/get_rooms/{user_id}")
async def get_rooms(user_id: str):
    return get_rooms_for_player(user_id)

@app.get("/get_room_details/{room_id}")
async def get_room_details_endpoint(room_id: str):
    return get_room_details(room_id)

@app.get("/get_regular_players/{user_id}")
async def get_regular_players_endpoint(user_id: str):
    regular_players = get_regular_players(user_id)
    return {"regular_players": regular_players}


# Define a Pydantic model for the command output.
class CommandOutput(BaseModel):
    action: str
    parameters: Optional[dict] = {}
    clarification: str = None

class ClarificationOutput(BaseModel):
    user_id: str
    buy_in: int

class CommandRequest(BaseModel):
    command: str
    user_id: str
    room_id: Optional[str] = None
    clarification_response: Optional[str] = None
    
@app.post("/execute_command/")
async def execute_command(payload: CommandRequest):
    command = payload.command
    logged_in_user = payload.user_id
    current_room = payload.room_id
    
    # Build a prompt that instructs Gemini on the desired output.
    # prompt = (
    #     "You are an assistant that converts natural language commands into a JSON object. "
    #     "Supported actions are: 'create_room', 'add_player', 'update_chips', and 'update_rebuy'.\n"
    #     "For 'create_room', required parameters: buy_in (integer) and rebuys (boolean). If missing, ask a clarifying question.\n"
    #     "For 'add_player', required parameters: room_id (string), user_id (string), and buy_in (integer). If missing, ask a clarifying question.\n"
    #     "For 'update_chips', required parameters: room_id (string), user_id (string), and chip_change (integer). If missing, ask a clarifying question.\n"
    #     "For 'update_rebuy', required parameters: room_id (string), user_id (string), and buy_in (integer). If missing, ask a clarifying question.\n"
    #     "If a clarifying question is needed, return a JSON with action set to 'ask_clarification' and include the question in the 'clarification' field.\n"
    #     "Otherwise, return a JSON with 'action' and 'parameters'.\n"
    #     f"Command: \"{command}\""
    # )
    prompt = (
        "You are an assistant that converts natural language commands into a JSON object. "
        "Supported actions are: 'create_room', 'add_player', 'update_chips', and 'update_rebuy'.\n"
        "For 'create_room', required parameters: buy_in (integer) and rebuys (boolean). If missing, ask a clarifying question.\n"
        "For 'add_player', required parameters: user_id (string) and buy_in (integer). Do not include room_id in your output, as it will be provided by the current context. "
        "If missing, ask: 'Please provide the player user id and buy-in details'\n"
        "For 'update_chips', required parameters: user_id (string) and new_chip_count (integer) representing the player's updated chip count. Do not include room_id in your output, as it will be provided by the current context."
        "Example: For the command \"update akshay's chips to 150\", return: {\"action\": \"update_chips\", \"parameters\": {\"user_id\": \"akshay\", \"new_chip_count\": 150}}.\n"
        "If missing, ask a clarifying question like 'What is the updated chip count for [user]?'\n"
        "For 'update_rebuy', required parameters: user_id (string), and buy_in (integer). Do not include room_id in your output, as it will be provided by the current context. If missing, ask a clarifying question.\n"
        "If a clarifying question is needed, return a JSON with action set to 'ask_clarification' and include the question in the 'clarification' field.\n"
        "Otherwise, return a JSON with 'action' and 'parameters'.\n"
        f"Command: \"{command}\""
    )
    # Create an output parser from our Pydantic model.
    output_parser = PydanticOutputParser(pydantic_object=CommandOutput)
    
    # Initialize the Gemini AI agent.
    ai = GoogleGenerativeAI(api_key=GEMINI_API_KEY, model= "gemini-1.5-pro-001", temperature=0)
    
    # Generate the response with structured output.
    ai_response = ai.generate([prompt])
    print(ai_response)

    
    try:
        # The parser will now guarantee that the response is structured as per CommandOutput.
        command_data = output_parser.parse(ai_response.generations[0][0].text)
    except Exception as e:
        return {"status": "error", "message": "Could not parse AI response", "error": str(e)}
    
    # If clarification is requested, return the question.
    if command_data.action == "ask_clarification" and command_data.clarification:
        return {"status": "clarification", "question": command_data.clarification}
    
    action = command_data.action
    parameters = command_data.parameters

    if action == "create_room": # Create a room with buy in 100 and rebuys allowed
        buy_in = parameters.get("buy_in")
        created_by = logged_in_user
        rebuys = parameters.get("rebuys", False)
        result = create_poker_room(buy_in, created_by, rebuys)
    elif action == "add_player":
        # For add_player, use the provided current room id.
        room_id_used = current_room
        user_id_param = parameters.get("user_id")
        buy_in_value = parameters.get("buy_in")
        # If either is missing, check if the client supplied a clarification_response.
        if not (user_id_param and buy_in_value):
            if payload.clarification_response:
                clarification_parser = PydanticOutputParser(pydantic_object=ClarificationOutput)
                try:
                    clar_data = clarification_parser.parse(payload.clarification_response)
                    room_id_used = current_room
                    user_id_param = clar_data.user_id
                    buy_in_value = clar_data.buy_in
                except Exception as e:
                    return {"status": "error", "message": "Could not parse clarification answer", "error": str(e)}
            else:
                return {"status": "error", "message": "Missing parameters for add_player"}
        result = add_player_to_room(room_id_used, user_id_param, buy_in_value)
    elif action == "update_chips":
        room_id = current_room
        user_id = parameters.get("user_id")
        new_chip_count = parameters.get("new_chip_count")
        result = update_chip_count(user_id, room_id, new_chip_count)
    elif action == "update_rebuy":
        room_id = current_room
        user_id = parameters.get("user_id")
        buy_in = parameters.get("buy_in")
        result = update_rebuy(user_id, room_id, buy_in)
    else:
        result = {"status": "error", "message": "Unsupported action"}
    
    return result

# Define a request model for sending messages.
class SendMessageRequest(BaseModel):
    room_id: str
    message: str

# Endpoint to send the game summary message.
@app.post("/send_message/")
async def send_message_endpoint(payload: SendMessageRequest):
    return send_game_summary_message(payload.room_id, payload.message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
