$(document).ready(function () {
    $(".add-new").click(function () {
        window.location.href = "/recipe/-1";
    });

    const recipe_matches = function (recipe, query) {
        let str_matches = (name) => name.toLowerCase().indexOf(query) > -1;

        name_matches = str_matches(recipe.name);
        ingredient_matches = recipe.ingredients
            .map((l) => l.ingredient)
            .some(str_matches);

        return name_matches || ingredient_matches;
    };

    $("#myInput").on("keyup", function () {
        var value = $(this).val().toLowerCase();
        $("#recipe-list li").filter(function (i, e) {
            var is_match = recipe_matches(recipes[i], value);
            $(this).toggle(is_match);
        });
    });
});
