<script>
    import Collapsible from './Collapsible.svelte';

	let weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun", ];
	let units = ["portioner", "ml", "g", "kg", ];

    export let menu;

    var new_menu = function(){
		var menus = menu.menus;
		var new_menu = {title: "", days: [], parts: [{ingredient: '', amount: 0, unit: 'g'}]};
		menus.push(new_menu);
		menu.menus = menus;

	};

    var new_part = function(i_menu){
		var submenu = menu.menus[i_menu];
		var new_part = {ingredient: '', amount: 0, unit: 'g'};
		// add a dummy new part
		submenu.parts.push(new_part);
		// re-assign rec to menu.menus to let
		// UI update
		menu.menus[i_menu] = submenu;
	};

    var delete_part = function(i_menu, i_part){
		var submenu = menu.menus[i_menu];
		// remove part from list
		submenu.parts.splice(i_part, 1);
		// re-assign rec to menu.menus to let
		// UI update
		menu.menus[i_menu] = submenu;
	};

    var delete_menu = function(i_menu){
		var menus = menu.menus;
		// remove part from list
		menus.splice(i_menu, 1);
		// re-assign rec to menu.menus to let
		// UI update
		menu.menu = menus;
	};

</script>

{#each menu.menus as rec, i}

<Collapsible >
	<div slot="static">
        <div class="row justify-content-end">
            <div class="col-1">
                <button on:click={() => delete_menu(i)} >
                    <svg viewBox="0 0 20 20" fill="none" >
                        <path d="M2 2L19 19" stroke="black" stroke-width="2"/>
                        <path d="M2 19L19 2" stroke="black" stroke-width="2"/>
                    </svg>                        
                </button>
            </div>
            <div class="col-3">
                <input type="text" class="form-control col-sm" bind:value={rec.title} />
            </div>
            <div class="col-8">
                {#each weekdays as weekday}
                <div class="form-check form-check-inline">
                    <input type=checkbox bind:group={rec.days} name="selected_days" value={weekday}>
                    <label class="form-check-label col-form-label-sm" for={weekday}>{weekday}</label>
                </div>
                {/each}
            </div>
        </div>
    </div>

    <div slot="collapsible">
    {#each rec.parts as part, j}
        <div class="row justify-content-end">
            <div class="col-3">
                <input type="text" class="form-control col-sm" bind:value={part.ingredient} />
            </div>
            <div class="col-2">
                <input type="number" class="form-control col-sm" bind:value={part.amount} />
            </div>
            <div class="col-3">
                <select class="form-control col-sm" value={part.unit}>
                    {#each units as unit}
                        <option value={unit}>
                            {unit}
                        </option>
                    {/each}
                </select>
            </div>
            <div class="col-1">
                <button on:click={() => delete_part(i, j)} >
                    <svg viewBox="0 0 20 20" fill="none" >
                        <path d="M2 2L19 19" stroke="black" stroke-width="2"/>
                        <path d="M2 19L19 2" stroke="black" stroke-width="2"/>
                    </svg>                        
                </button>
            </div>
        </div>
    {/each}
    <div class="row justify-content-end">
        <div class="col-1">
            <button on:click={() => new_part(i)} >
                <svg viewBox="0 0 20 20" fill="none" >
                    <path d="M10 1V19" stroke="black" stroke-width="2"/>
                    <path d="M1 10L19 10" stroke="black" stroke-width="2"/>
                </svg>                        
            </button>
        </div>
    </div>

    </div>

</Collapsible>
{/each}

<div class="row">
    <div class="col-1 text-start">
        <button on:click={() => new_menu()}>
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