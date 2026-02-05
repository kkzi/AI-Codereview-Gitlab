"""
首页路由模块
"""
from flask import Blueprint, redirect

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
def home():
    # The dashboard is now integrated into the Flask app.
    # Let /dashboard handle login redirect if needed.
    return redirect('/dashboard')
