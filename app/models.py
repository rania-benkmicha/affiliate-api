from flask_sqlalchemy import SQLAlchemy

#Creating the instance of the ORM

db = SQLAlchemy()



class Advertiser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    category = db.Column(db.String, nullable=False)

# Association table for many-to-many Editor ↔ Advertiser
editor_advertiser = db.Table(
    "editor_advertiser",
    db.Column("editor_id", db.Integer, db.ForeignKey("editor.id"), primary_key=True),
    db.Column("advertiser_id", db.Integer, db.ForeignKey("advertiser.id"), primary_key=True)
)
class Editor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    eligible_advertisers = db.relationship(
        "Advertiser",
        secondary=editor_advertiser,
        backref="eligible_editors"
    )


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    advertiser_id = db.Column(db.Integer, db.ForeignKey("advertiser.id"))
    editor_id = db.Column(db.Integer, db.ForeignKey("editor.id"))
    status = db.Column(db.String, default="pending")  # Status types : pending / approved / rejected

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String, nullable=False)
    advertiser_id = db.Column(db.Integer, db.ForeignKey("advertiser.id"), nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey("editor.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, nullable=False)
