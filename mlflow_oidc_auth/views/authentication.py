import secrets

from flask import redirect, session, url_for, render_template

import mlflow_oidc_auth.utils as utils
from mlflow_oidc_auth.auth import get_oauth_instance
from mlflow_oidc_auth.app import app
from mlflow_oidc_auth.config import config
from mlflow_oidc_auth.user import create_user, populate_groups, update_user


def login():
    app.logger.debug("Recieved login request")
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    app.logger.debug(f"session: {session.__dict__}")
    try:
        app.logger.debug(f"session['oauth_state']={session['oauth_state']}")
    except:
        app.logger.debug("Key 'oauth_state' not present in session")
    return get_oauth_instance(app).oidc.authorize_redirect(config.OIDC_REDIRECT_URI, state=state)


def logout():
    session.clear()
    if config.AUTOMATIC_LOGIN_REDIRECT:
        return render_template(
            "auth.html",
            username=None,
            provide_display_name=config.OIDC_PROVIDER_DISPLAY_NAME,
        )
    return redirect("/")


def callback():
    """Validate the state to protect against CSRF"""

    app.logger.debug("Recieved callback request")
    app.logger.debug(f"session: {session.__dict__}")
    app.logger.debug(f"state: {utils.get_request_param('state')}")
    try:
        app.logger.debug(f"session['oauth_state']={session['oauth_state']}")
    except:
        app.logger.debug("Key 'oauth_state' not present in session")
        
    if "oauth_state" not in session or utils.get_request_param("state") != session["oauth_state"]:
        return "Invalid state parameter", 401

    token = get_oauth_instance(app).oidc.authorize_access_token()
    app.logger.debug(f"Token: {token}")
    session["user"] = token["userinfo"]

    email = token["userinfo"]["email"]
    if email is None:
        return "No email provided", 401
    display_name = token["userinfo"]["name"]
    is_admin = False
    user_groups = []

    if config.OIDC_GROUP_DETECTION_PLUGIN:
        import importlib

        user_groups = importlib.import_module(config.OIDC_GROUP_DETECTION_PLUGIN).get_user_groups(token["access_token"])
    else:
        user_groups = token["userinfo"][config.OIDC_GROUPS_ATTRIBUTE]

    app.logger.debug(f"User groups: {user_groups}")

    available_groups = config.OIDC_GROUP_NAME + [config.OIDC_ADMIN_GROUP_NAME]
    filtered_user_groups = list(filter(lambda x: x in available_groups, user_groups))
    if config.OIDC_ADMIN_GROUP_NAME in user_groups:
        is_admin = True
    elif len(filtered_user_groups) == 0:
        return "User is not allowed to login", 401

    create_user(username=email.lower(), display_name=display_name, is_admin=is_admin)
    populate_groups(group_names=filtered_user_groups)
    update_user(email.lower(), filtered_user_groups)
    session["username"] = email.lower()
    # TODO: Need to revisit if we want to do this
    # as this may lead to problems if the user is added
    # to a group
    session[config.OIDC_GROUPS_ATTRIBUTE] = filtered_user_groups

    app.logger.debug(f"Session has been set: {session}")

    return redirect(url_for("oidc_ui"))
