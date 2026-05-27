from app import app


if __name__ == "__main__":
    print(" Starting Country Club Advisor Command Board on 127.0.0.1:8080")
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=True, use_reloader=False)
