"""Run the minimal configuration prototype for variant 17."""

from config import parse_config


def main(argv=None):
    """Print every user-configurable parameter as one key-value pair."""
    config = parse_config(argv)
    for name, value in vars(config).items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
