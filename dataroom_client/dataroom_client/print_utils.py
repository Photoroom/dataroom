
def print_error(string):
    print(f"\033[31m{string}\033[0m")  # noqa


def print_success(string):
    print(f"\033[32m{string}\033[0m")  # noqa


def print_status(string):
    print(string)  # noqa
