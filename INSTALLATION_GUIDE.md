# Installation Guide (React + Playwright + Django + Databases)

This guide sets up the complete project stack on a local machine.

## 1. What You Will Run
- React app: `http://localhost:3000`
- Django backend + APIs: `http://127.0.0.1:8000`
- Playwright tests against React app
- MySQL DB (default Django apps + healer service)
- PostgreSQL DB (test analytics app via DB router)

---

## 2. Prerequisites
- Node.js 18+ and npm
- Python 3.10+
- MySQL 8+
- PostgreSQL 14+
- Git
- (Optional) Ollama for LLM validation

---

## 3. Clone and Open Project
```bash
git clone <your-repo-url>
cd ecommerce-app
```

---

## 4. Setup React App Layer
From repo root:
```bash
npm install
```

Run React app:
```bash
npm start
```

Expected:
- App runs at `http://localhost:3000`

---

## 5. Setup Python / Django Layer

### 5.1 Create and activate virtualenv
```bash
cd ai-healer-django/flaky_healer
python3 -m venv venv
source venv/bin/activate
```

### 5.2 Install Django dependencies
If you have your own requirements file, use that. Otherwise install minimum required packages:
```bash
pip install django==5.0 djangorestframework djangorestframework-simplejwt mysqlclient psycopg2-binary django-admin-interface django-colorfield django-import-export
```

### 5.3 Verify Django settings
Main settings file:
- `ai-healer-django/flaky_healer/flaky_healer/settings.py`

By default it uses:
- MySQL DB: `ai_healer_service`
- PostgreSQL DB: `playwright_artifacts`

---

## 6. Setup Databases

## 6.1 MySQL setup (default DB)
Create DB:
```sql
CREATE DATABASE ai_healer_service;
```

Optional: import existing data dump (if needed):
```bash
mysql -u root -p ai_healer_service < /Users/arvind.kumar1/Desktop/ecommerce-app/ai_healer_service.sql
```

> If your MySQL user/password is different, update `settings.py` accordingly.

## 6.2 PostgreSQL setup (analytics DB)
Create user and DB (adjust password if needed):
```sql
CREATE USER xebia_ai WITH PASSWORD '@xebia_ai';
CREATE DATABASE playwright_artifacts OWNER xebia_ai;
```

Grant privileges:
```sql
GRANT ALL PRIVILEGES ON DATABASE playwright_artifacts TO xebia_ai;
```

---

## 7. Run Django Migrations
From `ai-healer-django/flaky_healer` with venv active:

### 7.1 Default DB migrations
```bash
python manage.py migrate --database=default
```

### 7.2 Test analytics migrations (PostgreSQL)
```bash
python manage.py migrate test_analytics --database=playwright
```

### 7.3 Create superuser
```bash
python manage.py createsuperuser
```

---

## 8. Seed/Login Test User for Playwright Auth
Playwright auth helper expects valid credentials for `/auth/login/`.

You can create a test user+client with:
```bash
python setup_test_user.py
```

Then update credentials in:
- `tests/utils/auth.ts`

Fields to match:
- `email`
- `password`
- `client_secret`

---

## 9. Run Django Server
From `ai-healer-django/flaky_healer`:
```bash
python manage.py runserver
```

Expected:
- Backend at `http://127.0.0.1:8000`
- Admin at `http://127.0.0.1:8000/admin/`
- Analytics dashboard at `http://127.0.0.1:8000/test-analytics/dashboard/`

---

## 10. Setup Playwright Test Layer
From repo root (`ecommerce-app`):

Install Playwright browsers once:
```bash
npx playwright install
```

Run all tests:
```bash
npx playwright test
```

Run a single spec:
```bash
npx playwright test tests/product/add-to-cart.spec.ts
```

Run with explicit run ID for analytics grouping:
```bash
RUN_ID=RUN_DEMO_001 npx playwright test tests/product/add-to-cart.spec.ts
```

---

## 11. Optional: Ollama LLM Validation Layer

Start Ollama service and pull model:
```bash
ollama pull qwen2.5:7b
```

Set env vars before starting Django:
```bash
export USE_LLM_VALIDATION=true
export LLM_VALIDATION_URL=http://127.0.0.1:11434/api/generate
export LLM_VALIDATION_MODEL=qwen2.5:7b
export LLM_VALIDATION_TIMEOUT_SECONDS=8
```

Then run Django server again.

---

## 12. Normal Local Run Order (Recommended)
Open 3 terminals:

Terminal A (React):
```bash
cd /Users/arvind.kumar1/Desktop/ecommerce-app
npm start
```

Terminal B (Django):
```bash
cd /Users/arvind.kumar1/Desktop/ecommerce-app/ai-healer-django/flaky_healer
source venv/bin/activate
python manage.py runserver
```

Terminal C (Tests):
```bash
cd /Users/arvind.kumar1/Desktop/ecommerce-app
npx playwright test
```

---

## 13. Verification Checklist
- React app opens on `:3000`
- Django admin opens on `:8000/admin`
- Login API works: `POST /auth/login/`
- Healer API works: `POST /api/heal/`
- Test results save: `POST /test-analytics/test-result/`
- Dashboard loads: `/test-analytics/dashboard/`

---

## 14. Common Issues and Fixes

### Issue: `TemplateDoesNotExist`
- Ensure server runs from correct directory:
  - `ai-healer-django/flaky_healer`
- Restart server.

### Issue: `column ... does not exist`
- Run migrations on correct DB (especially `--database=playwright` for `test_analytics`).

### Issue: Playwright auth fails 401
- Update `tests/utils/auth.ts` credentials from `setup_test_user.py` output.

### Issue: Data not saving in analytics
- Confirm Django server running.
- Confirm `sendToDjango` endpoint is reachable.
- Check DB router and PostgreSQL connectivity.

### Issue: LLM timeout/failure
- Increase `LLM_VALIDATION_TIMEOUT_SECONDS`.
- Verify Ollama is running and model is pulled.

---

## 15. Important Paths
- React app: `src/`
- Playwright tests: `tests/`
- Django project: `ai-healer-django/flaky_healer/`
- Healer app: `ai-healer-django/flaky_healer/curertestai/`
- Analytics app: `ai-healer-django/flaky_healer/test_analytics/`
- Flow docs: `README_AI_HEALER_FLOW.md`, `ai-healer-django/flaky_healer/README_AI_HEALER_FLOW.md`
