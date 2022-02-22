<script>
    import Collapsible from "./Collapsible.svelte";
    import RecipeDetail from "./RecipeDetail.svelte";

    export let units;
    let recipelist = [];

    // fetch all plans and fill plan-list
    fetch(`http://localhost:8000/api/recipe`)
        .then((response) => response.json())
        .then((data) => (recipelist = data));

    let new_recipe = () => {
        var min_id = Math.min(0, ...recipelist.map((recipe) => recipe.doc_id));
        var dummy = {
            name: "",
            placement: "",
            rating: 0,
            ingredients: [],
            doc_id: min_id - 1,
        };
        recipelist.push(dummy);
        recipelist = recipelist;
    };

    let delete_recipe = (doc_id) => {
        recipelist = recipelist.filter((plan) => plan.doc_id != doc_id);
    };

    let recipe_search = "";

    let recipe_is_match = (recipe, query) => {
        let title_matches = recipe.name.indexOf(query) > -1;
        let ingredients_match = recipe.ingredients.some(
            (rec) => rec.ingredient.indexOf(query) > -1
        );
        return title_matches || ingredients_match;
    };

    $: active_recipes = recipelist.filter((rec) =>
        recipe_is_match(rec, recipe_search)
    );

    let to_json = () => {
        // post updated recipes
        // then update local version with returned
        // data with new id's
        var json_recipes = JSON.stringify(active_recipes);
        console.log(json_recipes);

        fetch("http://localhost:8000/api/recipe", {
            method: "POST", // or 'PUT'
            mode: "cors",
            headers: {
                "Content-Type": "application/json",
            },
            body: json_recipes,
        })
            .then((response) => response.json())
            .then((data) => (recipelist = data));
    };
</script>

<div class="row">
    <div class="col-4">
        <h1>Recipes</h1>
    </div>
    <div class="col-2">
        <input
            type="text"
            class="form-control inline"
            bind:value={recipe_search}
        />
    </div>
    <div class="col-2">
        <button on:click={() => new_recipe()}>
            <svg viewBox="0 0 20 20" fill="none">
                <path d="M10 1V19" stroke="black" stroke-width="2" />
                <path d="M1 10L19 10" stroke="black" stroke-width="2" />
            </svg>
        </button>
    </div>
</div>

{#each active_recipes as recipe}
    <div class="recipe-container">
        <Collapsible>
            <div slot="static" class="row  justify-content-end">
                <div class="col-2">
                    <button on:click={() => delete_recipe(recipe.doc_id)}>
                        <svg viewBox="0 0 20 20" fill="none">
                            <path
                                d="M2 2L19 19"
                                stroke="black"
                                stroke-width="2"
                            />
                            <path
                                d="M2 19L19 2"
                                stroke="black"
                                stroke-width="2"
                            />
                        </svg>
                    </button>
                </div>
                <div class="col-5">
                    <input
                        type="text"
                        class="form-control form-control-lg inline col-sm"
                        bind:value={recipe.name}
                    />
                </div>
                <div class="col-3">
                    <input
                        type="text"
                        class="form-control form-control-lg inline col-sm"
                        bind:value={recipe.placement}
                    />
                </div>
                <div class="col-2">
                    <input
                        type="text"
                        class="form-control form-control-lg inline col-sm"
                        bind:value={recipe.rating}
                    />
                </div>
            </div>
            <div slot="collapsible">
                <RecipeDetail {recipe} {units} />
            </div>
        </Collapsible>
    </div>
{/each}

<button on:click={() => to_json()}> send </button>

<style>
    button {
        background-color: var(--background, #fff);
        color: var(--gray-darkest, #282828);
        display: inline;
        justify-content: space-between;
        border: none;
        margin: 0;
        padding: 1em 0.5em;
        outline: none;
    }

    button svg {
        outline: none;
    }

    svg {
        height: 0.7em;
        width: 0.7em;
    }

    div.plan-container {
        padding: 1em 0.5em;
        border-bottom: 3px solid darkslategrey;
    }
</style>
