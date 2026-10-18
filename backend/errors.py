from flask import jsonify
from werkzeug.exceptions import HTTPException

MESSAGES = {
    404: "Not found.",
    405: "Method not allowed.",
    500: "Internal server error.",
}


def error_response(message, status, **extra):
    """Build the standard error reply: error_response("Reason is required.", 422)."""
    return jsonify(error=message, **extra), status


def register_error_handlers(app):
    """Make Flask's own errors (unknown URL, wrong method, crashes) return JSON too."""

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = MESSAGES.get(error.code) or error.description or error.name
        return jsonify(error=message), error.code