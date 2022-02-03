<svelte:head>
	<!-- Font Awesome -->
	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.8.2/css/all.css">
	<!-- Google Fonts -->
	<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto:300,400,500,700&display=swap">
	<!-- Bootstrap core CSS -->
	<link href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/4.4.1/css/bootstrap.min.css" rel="stylesheet">
	<!-- Material Design Bootstrap -->
	<link href="https://cdnjs.cloudflare.com/ajax/libs/mdbootstrap/4.16.0/css/mdb.min.css" rel="stylesheet">
</svelte:head>



<script>
	import MenuList from './MenuList.svelte';
	import IngredientList from './IngredientList.svelte';

	let navigation_bar = [
		{caption: "ingredient", navid: "ingredient"},
		{caption: "recipe", navid: "recipe"},
		{caption: "plan", navid: "plan"},
	];
	let navchoice = "plan";
	let doc_id = -1; // if doc_id >0 edit a doc otherwise show list view

	function handleMessage(event) {
		doc_id = event.detail.doc_id;
	}


</script>


<main>
	<nav class="navbar navbar-expand-md navbar-dark bg-dark mb-4">
	<div class="container-fluid">
		<a class="navbar-brand" href="#">Menu editor</a>
		<div class="collapse navbar-collapse" id="navbarCollapse">
		<ul class="navbar-nav me-auto mb-2 mb-md-0">
			{#each navigation_bar as {caption, navid}}
				<li class="nav-item">
    				<a class="nav-link" href="/" on:click|preventDefault={() => (navchoice = navid, doc_id=-1)}> {caption} </a>
				</li>
			{/each}
		</ul>
		</div>
	</div>
	</nav>

    
{#if navchoice === "plan"}
    <MenuList/>
{:else if navchoice === "ingredient"}
	<IngredientList/>
{:else}
	<p>unknown choice</p>
{/if}

</main>

<style>
	main {
		text-align: center;
		padding: 1em;
		max-width: 240px;
		margin: 0 auto;
	}

	h1 {
		color: #ff3e00;
		text-transform: uppercase;
		font-size: 4em;
		font-weight: 100;
	}

	@media (min-width: 640px) {
		main {
			max-width: none;
		}
	}
</style>