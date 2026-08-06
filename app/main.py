from flask import Flask, request, jsonify
from logging_config import configure_logging
from services.pipeline import AuditPipeline

configure_logging()

app = Flask(__name__)

pipeline = AuditPipeline()


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "GEO Auditor",
        "endpoints": [
            "/audit",
            "/health"
        ]
    })


@app.route("/audit", methods=["POST"])
def audit():
    data = request.get_json(silent=True) or {}

    url = data.get("url", "").strip()

    if not url:
        return jsonify({
            "error": "Missing 'url' in request body."
        }), 400

    try:
        result = pipeline.run(url)

        return jsonify({
            "message": "Audit completed successfully.",
            "report": result["report"],
            "geo_score": result["scores"].geo,
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy"
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")