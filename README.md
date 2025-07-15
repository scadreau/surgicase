# SurgiCase Management API

This project provides a FastAPI-based REST API for managing users, cases, facilities, and surgeons, with data stored in a MySQL RDS database. AWS Secrets Manager is used for secure credential management. The API is suitable for healthcare or case management applications and supports full CRUD operations for users, cases, facilities, and surgeons.

## Features
- User, case, facility, and surgeon management
- Secure database credential retrieval via AWS Secrets Manager
- CRUD operations for all entities
- Health check endpoint
- Pydantic models for data validation

## Requirements
- Python 3.7+
- [FastAPI](https://fastapi.tiangolo.com/)
- [Uvicorn](https://www.uvicorn.org/)
- [PyMySQL](https://pymysql.readthedocs.io/)
- [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [pydantic](https://pydantic-docs.helpmanual.io/)

## Installation
1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd <your-repo-directory>
   ```
2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install fastapi uvicorn pymysql boto3 pydantic
   ```

## Running the Application
To start the API server:
```bash
python fapi_case_user.py
```
This will start the server at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## API Endpoints

### User Endpoints
- `GET /user?user_id=...` — Retrieve user information by user ID
- `POST /user` — Add a new user
- `PATCH /user` — Update user fields (requires user_id and at least one field to update)
- `DELETE /user?user_id=...` — Deactivate (soft delete) a user by user ID

### Case Endpoints
- `GET /case?case_id=...` — Retrieve case information by case ID
- `POST /case` — Add a new case and its procedure codes
- `PATCH /case` — Update case fields and/or replace procedure codes (requires case_id)
- `DELETE /case?case_id=...` — Deactivate (soft delete) a case by case ID

### Facility Endpoints
- `POST /facility` — Add a new facility for a user
- `DELETE /facility?facility_id=...` — Delete a facility by facility ID
- `GET /facilities?user_id=...` — Get all facilities for a user

### Surgeon Endpoints
- `POST /surgeon` — Add a new surgeon for a user
- `DELETE /surgeon?surgeon_id=...` — Delete a surgeon by surgeon ID
- `GET /surgeons?user_id=...` — Get all surgeons for a user

### Health Check
- `GET /health` — Returns `{ "status": "healthy" }` if the service is running

## Data Models
- **User**: user_id, user_email, first_name, last_name, address, city, state, zipcode, telephone, user_npi, referred_by_user, message_pref, states_licensed
- **Case**: user_id, case_id, case_date, surgeon_id, facility_id, patient (first, last, ins_provider), procedure_codes
- **Facility**: user_id, facility_name
- **Surgeon**: user_id, first_name, last_name

## Security & Configuration
- Database credentials are retrieved from AWS Secrets Manager. Ensure your AWS credentials and region are configured in your environment.
- The API expects the necessary secrets to be present in AWS Secrets Manager.

