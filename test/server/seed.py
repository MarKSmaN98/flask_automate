from config import app, db
from models import User

with app.app_context():
    User.query.delete()
    user = User(name="Example User")
    db.session.add(user)
    db.session.commit()
