ALLOWED_DISPLAY_ROLES = {"SUPER_ADMIN", "ADMIN", "PLAYER"}


def filter_role_names(roles):
    names = []
    for role in roles or []:
        name = role if isinstance(role, str) else getattr(role, "name", None)
        if name in ALLOWED_DISPLAY_ROLES:
            names.append(name)
    return names
