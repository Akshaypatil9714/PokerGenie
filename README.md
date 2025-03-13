# Poker Game Room Web Application

This is a comprehensive AI-powered Poker Game Room web application built with React for the frontend, FastAPI for the backend, and Firebase as the database. It incorporates real-time game management, player authentication, and advanced AI-driven command execution using Google Gemini.

## Features

- **User Registration & Authentication**

    - Players can register and authenticate using a secure password hashing mechanism.

- **Room Management**

    - Create poker rooms specifying initial buy-in amounts and optional rebuy settings.

    - Manage player participation and game state dynamically.

- **Chip Management**

    - Track player chip counts, allowing dynamic updates throughout gameplay.

    - Handle player rebuys seamlessly.

- **Game Settlement**

    - Automatically calculates game outcomes, displaying profits, losses, and debts.

    - Provides a summary of the game with player balances, rebuys, and final chip counts.

- **AI Command Processing**

    - Utilize Google's Gemini API to interpret and execute natural language commands for smoother gameplay management.

    - Supports both text and voice-based commands for enhanced user interaction.


## Technology Stack

- **Frontend**: React.js

- **Backend**: FastAPI (Python)

- **Database**: Firebase (Firestore)

- **AI Integration**: Google Gemini API

## API Endpoints

- **/register_player**: Register a new player.

- **/authenticate_player/**: Authenticate player login.

- **Game Management APIs**: /create_room/, /add_player/, /update_chip_count/, /update_rebuy/, /settle_game/

- **AI Integration**: Endpoint to handle natural language and voice-based game commands.

## Installation

**Clone the repository:**

```bash
    git clone <repository-url>
```

**Install dependencies:**

```bash
    npm install
    pip install -r requirements.txt
```

**Setup Firebase credentials in .env:**
```bash
    FIREBASE_KEY_JSON='<your-firebase-key-json>'
    GEMINI_API_KEY='<your-gemini-api-key>'
```

**Run backend:**
```bash
    uvicorn main:app --reload
```

**Install dependencies:**
```bash
    npm install
```

**Start frontend server:**
```bash
    npm run dev
```

## Usage

- Open your browser and navigate to http://localhost:3000.
    
- Register or login.

- Create and manage poker rooms.

- Add players and track their chip counts.

- Execute game commands either manually or through AI commands.

## Contributing

Contributions and suggestions are welcome. Please create a pull request or submit issues for bugs or feature requests.

## License

Distributed under the MIT License. See LICENSE for more information.

## Contact

For queries or contributions, please contact via GitHub issues.