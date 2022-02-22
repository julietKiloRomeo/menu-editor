<script>
	export let units;

    export let recipe;

    var new_ingredient = function(){
		var ingredients = recipe.ingredients;
		var new_ingredient = {ingredient: '', amount: 0, unit: 'g'};
		ingredients.push(new_ingredient);
		recipe.ingredients = ingredients;
	};

    var delete_ingredient = function(i){
		var ingredients = recipe.ingredients;
		ingredients.splice(i, 1);
		recipe.ingredients = ingredients;
	};

</script>


{#each recipe.ingredients as ingredient, i}
    <div class="row justify-content-end">
        <div class="col-3">
            <input type="text" class="form-control col-sm" bind:value={ingredient.ingredient} />
        </div>
        <div class="col-2">
            <input type="number" class="form-control col-sm" bind:value={ingredient.amount} />
        </div>
        <div class="col-3">
            <select class="form-control col-sm" value={ingredient.unit}>
                {#each units as unit}
                    <option value={unit}>
                        {unit}
                    </option>
                {/each}
            </select>
        </div>
        <div class="col-1">
            <button on:click={() => delete_ingredient(i, j)} >
                <svg viewBox="0 0 20 20" fill="none" >
                    <path d="M2 2L19 19" stroke="black" stroke-width="2"/>
                    <path d="M2 19L19 2" stroke="black" stroke-width="2"/>
                </svg>                        
            </button>
        </div>
    </div>
{/each}


<div class="row">
    <div class="col-1 text-start">
        <button on:click={() => new_ingredient()}>
            <svg viewBox="0 0 20 20" fill="none" >
                <path d="M10 1V19" stroke="black" stroke-width="2"/>
                <path d="M1 10L19 10" stroke="black" stroke-width="2"/>
            </svg>
        </button>
    </div>
</div>





<style>
    button {
      background-color: var(--background, #fff);
      color: var(--gray-darkest, #282828);
      display: inline;
      justify-content: space-between;
      width: 100%;
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
  </style>