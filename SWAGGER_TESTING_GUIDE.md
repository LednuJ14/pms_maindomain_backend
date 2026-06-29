# Swagger Testing Guide

## How to Access Swagger UI

1. **Start the backend server:**
   ```bash
   cd main-domain/backend
   python app.py
   ```
   Server runs on: `http://localhost:5000`

2. **Open Swagger UI in browser:**
   ```
   http://localhost:5000/api/docs/
   ```

3. **View the API specification JSON:**
   ```
   http://localhost:5000/api/swagger.json
   ```

## Testing Endpoints

### Step 1: Get Authentication Token

1. In Swagger UI, find **Authentication** section
2. Expand **POST /api/auth/login**
3. Click **"Try it out"**
4. Enter test credentials:
   ```json
   {
     "email": "tenant@example.com",
     "password": "Tenant123!"
   }
   ```
5. Click **"Execute"**
6. Copy the `access_token` from the response

### Step 2: Authorize in Swagger

1. Click the **"Authorize"** button (top right, lock icon)
2. In the "Value" field, enter:
   ```
   Bearer YOUR_ACCESS_TOKEN_HERE
   ```
   (Replace `YOUR_ACCESS_TOKEN_HERE` with the token from Step 1)
3. Click **"Authorize"** then **"Close"**

### Step 3: Test Protected Endpoints

1. Find any protected endpoint (e.g., **GET /api/auth/me**)
2. Click **"Try it out"**
3. Click **"Execute"**
4. You should see your user information in the response

## What Errors Appear in Swagger?

### ✅ Errors That WILL Show in Swagger:

1. **Validation Errors (400)**
   - Missing required fields
   - Invalid data format
   - Example: `{"error": "Email is required"}`

2. **Authentication Errors (401)**
   - Invalid token
   - Expired token
   - Example: `{"error": "Token has expired"}`

3. **Authorization Errors (403)**
   - Insufficient permissions
   - Example: `{"error": "Admin access required"}`

4. **Not Found Errors (404)**
   - Resource doesn't exist
   - Example: `{"error": "User not found"}`

5. **Server Errors (500)**
   - Database errors
   - Application errors
   - Example: `{"error": "Internal server error"}`

### ❌ Errors That WON'T Show in Swagger:

1. **Swagger Documentation Errors**
   - Malformed docstrings won't show errors in UI
   - Routes just won't appear if docstrings are invalid
   - Check browser console (F12) for JavaScript errors

2. **Server Startup Errors**
   - If server fails to start, Swagger won't be accessible
   - Check terminal/console for Python errors

3. **Network Errors**
   - Connection refused
   - CORS errors (check browser console)

## Troubleshooting

### Problem: "No operations defined in spec!"

**Solution:**
- Routes need Swagger docstrings to appear
- Check that routes have proper YAML docstrings with `---` separator
- Verify routes start with `/api/` (Swagger is filtered to `/api/*` routes)

### Problem: Routes don't appear

**Check:**
1. Route must start with `/api/`
2. Route must have Swagger docstring with:
   ```python
   """
   Route description
   ---
   tags:
     - TagName
   summary: Brief summary
   ...
   """
   ```
3. Restart server after adding docstrings

### Problem: "Failed to fetch" error

**Check:**
1. Server is running on port 5000
2. No CORS errors in browser console (F12)
3. Network tab shows the actual error

### Problem: Authorization not working

**Check:**
1. Token format: `Bearer YOUR_TOKEN` (include "Bearer " prefix)
2. Token is not expired
3. Token is valid (try login endpoint first)

## Testing Checklist

- [ ] Swagger UI loads at `/api/docs/`
- [ ] Routes are visible and organized by tags
- [ ] Can view request/response schemas
- [ ] Can test public endpoints (login, register)
- [ ] Can authorize with JWT token
- [ ] Can test protected endpoints
- [ ] Error responses show correctly
- [ ] Response schemas match actual responses

## Example Test Flow

1. **Test Public Endpoint:**
   - POST `/api/auth/register` - Create test user
   - POST `/api/auth/login` - Get token

2. **Authorize:**
   - Click "Authorize" button
   - Enter token: `Bearer <token>`

3. **Test Protected Endpoint:**
   - GET `/api/auth/me` - Get current user
   - GET `/api/properties` - List properties

4. **Test Error Cases:**
   - POST `/api/auth/login` with wrong password → 401
   - GET `/api/users` without admin token → 403
   - GET `/api/users/999` with invalid ID → 404

## Viewing Raw Swagger JSON

To see the complete API specification:
```
http://localhost:5000/api/swagger.json
```

This shows all documented routes, schemas, and parameters in JSON format.

