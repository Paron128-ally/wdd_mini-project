import os

from personal_expense_ttracker.app import app


if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=os.environ.get("FLASK_DEBUG") == "1")
