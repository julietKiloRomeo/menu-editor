<script>
    // based on suggestions from:
    // Inclusive Components by Heydon Pickering https://inclusive-components.design/collapsible-sections/
    let expanded = false;
    export let justification = "";
</script>

<div class="collapsible">
    <div class={"row " + justification}>
        <slot name="static"></slot>
        <div class="col-1">
            <button aria-expanded={expanded} on:click={() => expanded = !expanded}>
                <svg viewBox="0 0 20 20" fill="none" >
                    <path class="expand" d="M 1 10 l 9 9 l 9 -9" stroke="black" stroke-width="2"/>
                    <path class="collapse" d="M 1 10 l 9 -9 l 9 9" stroke="black" stroke-width="2"/>
                </svg>
            </button>
        </div>
    </div>
    <div hidden={!expanded}>
        <slot name="collapsible"></slot>
    </div>
</div>

<style>

	
  button {
    background-color: var(--background, #fff);
    color: var(--gray-darkest, #282828);
    display: flex;
	justify-content: space-between;
    width: 100%;
	border: none;
	margin: 0;
	padding: 1em 0.5em;
    outline: none;
  }


  button[aria-expanded="true"] .expand {
      display: none;
  }
  button[aria-expanded="false"] .expand {
      display: inline;
  }
  button[aria-expanded="true"] .collapse {
      display: inline;
  }
  button[aria-expanded="false"] .collapse {
      display: none;
  }

  button svg{
      outline: none;
  }

  svg {
      height: 0.7em;
	  width: 0.7em;
  }
</style>