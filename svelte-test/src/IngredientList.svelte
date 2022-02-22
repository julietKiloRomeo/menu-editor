<script>    

    import Collapsible from './Collapsible.svelte';

	let ingredientlist = [];
    export let categories;

    // fetch all plans and fill plan-list
	fetch(`http://localhost:8000/api/ingredient`)
	.then(response => response.json())
	.then(data => ingredientlist=data );

    let new_ingredient = () => {
        var min_id = Math.min( 0, ...ingredientlist.map(ingredient => ingredient.doc_id) )
        var dummy = {
            name: "",
            category: "",
            alii: [],
            doc_id: min_id - 1,
        };
        ingredientlist.push(dummy);
        ingredientlist = ingredientlist;
    };

    let delete_ingredient = (doc_id) => {

        fetch('http://localhost:8000/api/ingredient/delete', {
            method: 'POST', // or 'PUT'
            mode: 'cors',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify([doc_id]),
        })
        .then(response => response.json())
    	.then(data => ingredientlist=data );        
        
    };

    let ingredient_search = "";
    let category_search = "All";

    $: active_ingredients = ingredientlist.filter(
            ingredient => ingredient.name.indexOf(ingredient_search) > -1
        ).filter(
            ingredient => category_search === "All" | ingredient.category === category_search
        );


    let to_json = () => {
        var json_ingredients = JSON.stringify(active_ingredients);
        console.log(json_ingredients);

        fetch('http://localhost:8000/api/ingredient', {
            method: 'POST', // or 'PUT'
            mode: 'cors',
            headers: {
                'Content-Type': 'application/json',
            },
            body: json_ingredients,
        })
        .then(response => response.json())
    	.then(data => ingredientlist=data );
    };

</script>


<div class="row pb-5">
    <div class="col-4">
        <h1>Ingredients</h1>
    </div>
    <div class="col-2">
        <input type="text" class="form-control inline" bind:value={ingredient_search} />
    </div>

    <div class="col-2">
        <select class="form-control col-sm" bind:value={category_search}>
            {#each ["All", ...categories] as cat}
                <option value={cat}>
                    {cat}
                </option>
            {/each}
        </select>
    </div>

    <div class="col-2">
        <button on:click={() => new_ingredient()}>
            <svg viewBox="0 0 20 20" fill="none" >
                <path d="M10 1V19" stroke="black" stroke-width="2"/>
                <path d="M1 10L19 10" stroke="black" stroke-width="2"/>
            </svg>                
        </button>
    </div>
</div>

{#each active_ingredients as ingredient}
    <div class="row justify-content-end">
        <div class="col-2">
            <input type="text" class="form-control form-control-lg inline col-sm" bind:value={ingredient.name} />
        </div>
        <div class="col-2">
            <select class="form-control col-sm" bind:value={ingredient.category}>
                {#each categories as cat}
                    <option value={cat}>
                        {cat}
                    </option>
                {/each}
            </select>
        </div>
        <div class="col-2">
            <input type="text" class="form-control form-control-lg inline col-sm" bind:value={ingredient.alii} />
        </div>
        <div class="col-2">
            <button on:click={() => delete_ingredient(ingredient.doc_id)}>
                <svg viewBox="0 0 20 20" fill="none" >
                    <path d="M2 2L19 19" stroke="black" stroke-width="2"/>
                    <path d="M2 19L19 2" stroke="black" stroke-width="2"/>
                </svg>                  
            </button>
        </div>
    </div>
{/each}

<button on:click={() => to_json()}>
    send            
</button>



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
  
    button svg{
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