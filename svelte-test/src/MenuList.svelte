<script>    

    import Collapsible from './Collapsible.svelte';
    import MenuDetail from './MenuDetail.svelte';

	let planlist = [];

    // fetch all plans and fill plan-list
	fetch(`http://localhost:8000/api/menu`)
	.then(response => response.json())
	.then(data => planlist=data );

    let new_plan = () => {
        var min_id = Math.min( 0, ...planlist.map(plan => plan.id) )
        var dummy = {
            name: "",
            rating: 0,
            menus: [],
            id: min_id - 1,
        };
        planlist.push(dummy);
        planlist = planlist;
    };
    let delete_plan = (doc_id) => {
        planlist = planlist.filter( plan => plan.id != doc_id  );
    };
    let plan_search = "";

    $: active_plans = planlist.filter( plan => plan.name.indexOf(plan_search) > -1 );

</script>


<div class="row">
    <div class="col-4">
        <h1>Plans</h1>
    </div>
    <div class="col-2">
        <input type="text" class="form-control inline" bind:value={plan_search} />
    </div>
    <div class="col-2">
        <button on:click={() => new_plan()}>
            <svg viewBox="0 0 20 20" fill="none" >
                <path d="M10 1V19" stroke="black" stroke-width="2"/>
                <path d="M1 10L19 10" stroke="black" stroke-width="2"/>
            </svg>                
        </button>
    </div>
</div>

{#each active_plans as plan}
    <div class="plan-container">
    <Collapsible >
        <div slot="static" class="row">
            <div class="col-2">
                <button on:click={() => delete_plan(plan.id)}>
                    <svg viewBox="0 0 20 20" fill="none" >
                        <path d="M2 2L19 19" stroke="black" stroke-width="2"/>
                        <path d="M2 19L19 2" stroke="black" stroke-width="2"/>
                    </svg>                
                </button>
            </div>
            <div class="col-10">
                <input type="text" class="form-control form-control-lg inline col-sm" bind:value={plan.name} />
            </div>
        </div>
        <div slot="collapsible">
            <MenuDetail menu={plan}>
            </MenuDetail>
        </div>
    </Collapsible >
    </div>
{/each}


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