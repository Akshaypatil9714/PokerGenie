import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import hashlib
import math

# Load environment variables from the correct directory
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path)


# Ensure Firebase is initialized only once
if not firebase_admin._apps:
    firebase_key_json = os.getenv("FIREBASE_KEY_JSON")

    if not firebase_key_json:
        raise ValueError("Firebase key not found in environment variables!")

    try:
        firebase_key_dict = json.loads(firebase_key_json)  # Convert string to dict
        cred = credentials.Certificate(firebase_key_dict)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully!")
    except Exception as e:
        raise ValueError(f"Firebase initialization failed: {e}")

db = firestore.client()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Register a new player (Sign-Up)
def register_player(user_id: str, player_name: str, password: str, phone: str = None):
    player_query = db.collection("players").where("user_id", "==", user_id).get()
    if player_query:
        return {"status": "error", "message": "User already exists"}
    
    hashed_password = hash_password(password)
    player_data = {
        "user_id": user_id,
        "name": player_name,
        "password": hashed_password,
        "total_buy_ins": 0,
        "historical_buy_ins": [],
        "chip_count": 0,
        "phone": phone
    }
    db.collection("players").document(user_id).set(player_data)
    return {"status": "success", "message": "Player registered successfully"}

# Authenticate a player (Login)
def authenticate_player(user_id: str, password: str):
    if not user_id:
        return {"status": "error", "message": "User ID cannot be empty"}

    player_ref = db.collection("players").document(user_id).get()
    if not player_ref.exists:
        return {"status": "error", "message": "User not found"}

    player_data = player_ref.to_dict()
    if player_data["password"] != hash_password(password):
        return {"status": "error", "message": "Incorrect password"}

    return {"status": "success", "player": player_data}  # Ensure valid response

def create_room_session(room_id: str, created_by: str, buy_in: int):
    """
    Creates a room session document that stores room-specific player data.
    Each player entry contains their initial buy_in and current chip_count.
    """
    session_data = {
        "players": {
            created_by: {
                "buy_in": buy_in,
                "chip_count": buy_in,
                "rebuys": []
            }
        }
    }
    db.collection("room_sessions").document(room_id).set(session_data)
    
def update_room_session_player(room_id: str, user_id: str, buy_in: int):
    """
    Adds a new player to the room session with their initial buy_in and chip_count.
    """
    session_ref = db.collection("room_sessions").document(room_id)
    # Use set with merge=True so that other players are not overwritten.
    session_ref.set({
        "players": {
            user_id: {
                "buy_in": buy_in,
                "chip_count": buy_in,
                "rebuys": []
            }
        }
    }, merge=True)

def update_room_session_chip_count(room_id: str, user_id: str, new_chip_value: int):
    """
    Updates a specific player’s chip count in the room session.
    """
    session_ref = db.collection("room_sessions").document(room_id)
    session_ref.update({
        f"players.{user_id}.chip_count": new_chip_value
    })
    
def update_room_session_rebuy(room_id: str, user_id: str, additional_buy_in: int):
    """
    Processes a rebuy by increasing both the player's total buy_in and chip_count.
    """
    session_ref = db.collection("room_sessions").document(room_id)
    session = session_ref.get()
    if not session.exists:
        return {"status": "error", "message": "Room session not found"}
    session_data = session.to_dict()
    player_data = session_data.get("players", {}).get(user_id)
    if not player_data:
        return {"status": "error", "message": "Player not found in room session"}
    # new_buy_in = player_data["buy_in"] + additional_buy_in
    new_chip_count = player_data["chip_count"] + additional_buy_in
    # new_rebuy_total = player_data.get("rebuy_total", 0) + additional_buy_in
    current_rebuys = player_data.get("rebuys", [])
    current_rebuys.append(additional_buy_in)
    session_ref.update({
        f"players.{user_id}": {
            "buy_in": player_data["buy_in"],
            "chip_count": new_chip_count,
            "rebuys": current_rebuys
        }
    })
    return {"message": f"Player {user_id} rebought chips for {additional_buy_in}", "rebuy_total": current_rebuys}

def get_room_session(room_id: str):
    session_ref = db.collection("room_sessions").document(room_id)
    session = session_ref.get()
    if session.exists:
        return session.to_dict()
    return None

#Creating a New Poker Room
def create_poker_room(buy_in: int, created_by: str, rebuys: bool):
    room_id = f"room_{int(datetime.utcnow().timestamp())}"
    room_data = {
        "room_id": room_id,
        "buy_in": buy_in,
        "rebuys": rebuys,
        "players": [created_by],
        "status": "active",
        "created_by": created_by,
    }
    db.collection("games").document(room_id).set(room_data)
    
    # Create a room session to track room-specific transactions.
    create_room_session(room_id, created_by, buy_in)
    
    return {"message": "Room created successfully!", "room_id": room_id}

# Get the latest created room_id
def get_latest_room_id():
    rooms = db.collection("games").order_by("room_id", direction=firestore.Query.DESCENDING).limit(1).stream()
    for room in rooms:
        return room.id
    return None

# Add player to a room (create profile if doesn't exist)
def add_player_to_room(room_id: str, user_id: str, buy_in: int):
    room_ref = db.collection("games").document(room_id)
    room_doc = room_ref.get()
    if not room_doc.exists:
        return {"status": "error", "message": "Room not found"}
    
    room_data = room_doc.to_dict()
    # Check if player already exists in the room
    if user_id in room_data.get("players", []):
        return {"status": "error", "message": "Player already exists in the room"}
    
    player_ref = db.collection("players").document(user_id)
    player_doc = player_ref.get()
    if not player_doc.exists:
        # return {"status": "error", "message": "Player not registered"}
        default_player_data = {
            "user_id": user_id,
            "name": f"Guest_{user_id}",  # Default name for unregistered players
            "password": None,  # No password for guest players
            "total_buy_ins": 0,
            "historical_buy_ins": [],
            "chip_count": 0
        }
        db.collection("players").document(user_id).set(default_player_data)
    
    # player_data = player_doc.to_dict()
    # player_name = player_data.get("name", "Unknown")
        
    # Add player to room
    room_ref.update({
         "players": firestore.ArrayUnion([user_id])
    })
    
    # Update the room session to record the player's buy-in
    update_room_session_player(room_id, user_id, buy_in)
    
    return {
        "message": f"Player {user_id} added to room {room_id} with buy-in {buy_in}",
        "user_id": user_id
    }

def update_chip_count(user_id: str, room_id: str, new_chip_value: int):
    update_room_session_chip_count(room_id, user_id, new_chip_value)
    return {"message": f"Player {user_id} chip count updated by {new_chip_value}"}

# Track and update rebuys per player
def update_rebuy(user_id: str, room_id: str, additional_buy_in: int):
    player_ref = db.collection("players").document(user_id)
    player = player_ref.get()
    if not player.exists:
        return {"status": "error", "message": "Player not found"}
    
    room_ref = db.collection("games").document(room_id)
    room = room_ref.get()
    if not room.exists:
        return {"status": "error", "message": "Room not found"}
    
    room_data = room.to_dict()
    if not room_data.get("rebuys", False):
        return {"status": "error", "message": "Rebuys not allowed in this room"}
        
    return update_room_session_rebuy(room_id, user_id, additional_buy_in)

def get_regular_players(room_creator: str, min_games: int = 3):
    """
    Returns a list of players who have played with the room creator in at least min_games.
    """
    games = db.collection("games").where("players", "array_contains", room_creator).stream()
    frequency = {}
    for game in games:
        data = game.to_dict()
        players = data.get("players", [])
        for player in players:
            if player != room_creator:
                frequency[player] = frequency.get(player, 0) + 1
    # Filter players who have played with the creator frequently.
    regulars = [player for player, count in frequency.items() if count >= min_games]
    return regulars



# def settle_game(room_id: str):
#     room_ref = db.collection("games").document(room_id)
#     room = room_ref.get()
#     if not room.exists:
#         return {"status": "error", "message": "Room not found"}
    
#     session_data = get_room_session(room_id)
#     if not session_data:
#         return {"status": "error", "message": "Room session not found"}
    
#     players_data = session_data.get("players", {})
#     settle_table = []
#     max_rebuys = 0  # Determine the maximum number of rebuys among players
#     for user_id, data in players_data.items():
#         initial_buy_in = data.get("buy_in", 0)
#         chip_count = data.get("chip_count", 0)
#         rebuys = data.get("rebuys", [])
#         total_rebuys = sum(rebuys)
#         profit_loss_value = chip_count - (initial_buy_in + total_rebuys)
#         profit_loss_text = "profit" if profit_loss_value > 0 else ("loss" if profit_loss_value < 0 else "even")
#         if len(rebuys) > max_rebuys:
#             max_rebuys = len(rebuys)
#         settle_table.append({
#             "player": user_id,
#             "buy_in": initial_buy_in,
#             "rebuys": rebuys,  # Full list of rebuys
#             "total_rebuys": total_rebuys,
#             "final_chip_count": chip_count,
#             "profit_loss": profit_loss_text
#         })
    
#     return {
#         "message": "Game settled successfully",
#         "settle_table": settle_table,
#         "max_rebuys": max_rebuys  # Pass the maximum number of rebuys for dynamic table generation
#     }

def settle_game(room_id: str):
    room_ref = db.collection("games").document(room_id)
    room = room_ref.get()
    if not room.exists:
        return {"status": "error", "message": "Room not found"}
    
    session_data = get_room_session(room_id)
    if not session_data:
        return {"status": "error", "message": "Room session not found"}
    
    players_data = session_data.get("players", {})
    settle_table = []
    max_rebuys = 0  # Determine the maximum number of rebuys among players
    net_values = {}  # Map player -> net value (profit/loss)
    for user_id, data in players_data.items():
        initial_buy_in = data.get("buy_in", 0)
        chip_count = data.get("chip_count", 0)
        rebuys = data.get("rebuys", [])
        total_rebuys = sum(rebuys)
        net = chip_count - (initial_buy_in + total_rebuys)
        profit_loss_text = "profit" if net > 0 else ("loss" if net < 0 else "even")
        net_values[user_id] = net
        if len(rebuys) > max_rebuys:
            max_rebuys = len(rebuys)
        settle_table.append({
            "player": user_id,
            "buy_in": initial_buy_in,
            "rebuys": rebuys,         # list of individual rebuys
            "total_rebuys": total_rebuys,
            "final_chip_count": chip_count,
            "profit_loss": profit_loss_text,
            "net": net                # include numeric net for debt calculation
        })
    
    # Compute debts: players with net < 0 owe players with net > 0.
    winners = []
    losers = []
    for player, net in net_values.items():
        if net > 0:
            winners.append({"player": player, "net": net})
        elif net < 0:
            losers.append({"player": player, "net": -net})  # store positive value for deficit

    # Sort (optional) so largest amounts are handled first.
    winners.sort(key=lambda x: x["net"], reverse=True)
    losers.sort(key=lambda x: x["net"], reverse=True)
    
    debts = []
    i = 0
    j = 0
    while i < len(losers) and j < len(winners):
        loser = losers[i]
        winner = winners[j]
        amount = min(loser["net"], winner["net"])
        debts.append({"from": loser["player"], "to": winner["player"], "amount": amount})
        loser["net"] -= amount
        winner["net"] -= amount
        if loser["net"] == 0:
            i += 1
        if winner["net"] == 0:
            j += 1

    return {
        "message": "Game settled successfully",
        "settle_table": settle_table,
        "max_rebuys": max_rebuys,
        "debts": debts
    }

    
def get_rooms_for_player(user_id: str):
    """Retrieve all rooms in which the player is a participant."""
    rooms_query = db.collection("games").where("players", "array_contains", user_id).get()
    rooms = []
    for room in rooms_query:
        room_data = room.to_dict()
        room_data["room_id"] = room.id  # include the document ID
        rooms.append(room_data)
    return rooms


def get_room_details(room_id: str):
    """Retrieve details for a specific room along with detailed players info."""
    room_ref = db.collection("games").document(room_id)
    room = room_ref.get()
    if not room.exists:
        return {"status": "error", "message": "Room not found"}
    
    room_data = room.to_dict()
    room_data["room_id"] = room.id
    
    session_data = get_room_session(room_id)
    if session_data:
        room_data["room_session"] = session_data
    else:
        room_data["room_session"] = {}
        
    # Build a detailed list of players info using the players array and room session data
    players_info = []
    players_list = room_data.get("players", [])
    session_players = room_data["room_session"].get("players", {}) if room_data.get("room_session") else {}

    for uid in players_list:
        # Use room session data if available; fallback to default buy_in from the room.
        if uid in session_players:
            info = session_players[uid]
            players_info.append({
                "id": uid,
                "name": uid,  # or retrieve actual name from your players collection if needed
                "chips": info.get("chip_count", room_data.get("buy_in", 0))
            })
        else:
            players_info.append({
                "id": uid,
                "name": uid,
                "chips": room_data.get("buy_in", 0)
            })
    room_data["players_info"] = players_info
        
    return room_data

# Dummy function to simulate sending an SMS.
def send_sms(phone_number: str, message: str) -> bool:
    # In production, integrate with an SMS provider (e.g., Twilio)
    print(f"Sending SMS to {phone_number}: {message}")
    return True


def send_game_summary_message(room_id: str, message: str):
    # Retrieve the room from the "games" collection.
    room_ref = db.collection("games").document(room_id)
    room_doc = room_ref.get()
    if not room_doc.exists:
        return {"status": "error", "message": "Room not found"}
    
    room_data = room_doc.to_dict()
    players = room_data.get("players", [])
    
    sent = []
    failed = []
    for player_id in players:
        player_ref = db.collection("players").document(player_id)
        player_doc = player_ref.get()
        if player_doc.exists:
            player_data = player_doc.to_dict()
            phone = player_data.get("phone")
            if phone:
                if send_sms(phone, message):
                    sent.append(player_id)
                else:
                    failed.append(player_id)
            else:
                failed.append(player_id)
        else:
            failed.append(player_id)
    return {"status": "success", "sent": sent, "failed": failed}