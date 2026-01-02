import os
import click
import yaml
import pathlib


def get_recipe(name):
    recipe_pth = pathlib.Path.cwd() / f"recipes/{name}.yml"
    with recipe_pth.open("r") as f: 
        recipe = yaml.load(f, Loader=yaml.FullLoader)

    return recipe

def set_recipe(name, recipe):
    recipe_pth = pathlib.Path.cwd() / f"recipes/{name}.yml"
    with recipe_pth.open("w") as f: 
        yaml.dump(recipe, f)

    return recipe

def print_recipe(recipe):
    header = f"""
{recipe["navn"]} ( {recipe["antal"]} portioner )
    """
    click.echo(header)
    for navn, amount in recipe["ingredienser"].items():
        ingredient = f"{navn:40s}: {amount['amount']:5.0f} {amount['unit']:<s}"
        click.echo(ingredient)



@click.group()
def cli():
    pass


@cli.group()
def recipe():
    pass


@recipe.command()
@click.argument('name')
def show(name):
    recipe = get_recipe(name)
    print_recipe(recipe)


@recipe.command()
@click.argument('name')
@click.option('--dry/--force', default=False)
def edit(name,  dry):
    try:
        recipe = get_recipe(name)
    except FileNotFoundError:
        create_new = click.prompt('Recipe does not exist. Create it?', type=bool)

        if not create_new:
            return
        recipe = dict(
            navn = click.prompt('Navn', type=str),
            placering = click.prompt('Placering', type=str),
            antal = click.prompt('Antal portioner', type=int),
            ingredienser={},
        )
        

    while True:
        ingredient = click.prompt('Ingrediens', default="stop")
        if ingredient == "stop":
            break
        amount = click.prompt('Antal', type=float)
        unit = click.prompt('Enhed', type=str)
        recipe["ingredienser"][ingredient] = { "amount":amount, "unit":unit }


    print_recipe(recipe)

    if not dry:
        set_recipe(name, recipe)

if __name__ == '__main__':
    cli()