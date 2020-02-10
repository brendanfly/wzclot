
def get_int(val):

    if val is None or val == '':
        return 0
    else:
        return int(val)

# converts a checkbox value to true = checked or false != checked
def get_dropdown_to_boolean(key, data):

    if key in data:
        if data[key] == 'yes':
            return True

    #default to returning false
    return False


def is_power_of_two(n):
    """Return True if n is a power of two."""
    if n <= 0:
        return False
    else:
        return n & (n - 1) == 0