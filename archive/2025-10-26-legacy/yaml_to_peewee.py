import yaml
import peewee
import pathlib




def load_yaml_file(filename):
    with open(filename, 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

config = load_yaml_file('config.yml')

for category_name, category_order in config['kategorier'].items():
    category = Category.create(name=category_name, order=category_order)
