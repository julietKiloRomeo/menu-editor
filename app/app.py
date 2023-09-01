from flask import Flask, request, jsonify
from flask_pymongo import PyMongo

application = Flask(__name__)

application.config["MONGO_URI"] = 'mongodb://localhost:27017/flaskdb'

mongo = PyMongo(application)

import routes

if __name__ == "__main__":
    application.run(host='0.0.0.0', port=5000, debug=True)