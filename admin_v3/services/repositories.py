from flask import has_app_context

from exts import db


def commit_if_context():
    if has_app_context():
        db.session.commit()


def soft_active_query(model):
    query = model.query
    if hasattr(model, 'is_del'):
        query = query.filter(model.is_del == 0)
    return query


def first_active(model, *criteria):
    query = soft_active_query(model)
    for condition in criteria:
        query = query.filter(condition)
    return query.first()

