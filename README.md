# NagrikSetu

NagrikSetu is a Django-based citizen grievance platform for submitting, tracking, and managing municipal complaints.

## Features
- User signup / login
- Submit complaints with media attachments
- Role-based dashboards (citizen, corporator)
- REST API endpoints for integrations

## Quick setup

1. Create and activate a virtual environment:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Apply migrations and create a superuser:

```bash
python manage.py migrate
python manage.py createsuperuser
```

4. Run the development server:

```bash
python manage.py runserver
```

Media files are served from the `media/` directory during development. See `config/settings.py` for production configuration and environment-specific settings.

## Tests

Run tests with:

```bash
python manage.py test
```

## Contributing
Please open issues or pull requests. Keep changes small and focused.

## License
MIT (or specify your preferred license)
