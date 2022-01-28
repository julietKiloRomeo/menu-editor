$(document).ready(function () {
    $(".add-new").click(function () {
        window.location.href = "/menu/-1";
    });

    const menu_matches = function (menu, query) {
        let str_matches = (name) => name.toLowerCase().indexOf(query) > -1;

        name_matches = str_matches(recipe.name);
        return name_matches
    };

    $("#myInput").on("keyup", function () {
        var value = $(this).val().toLowerCase();
        $("#recipe-list li").filter(function (i, e) {
            var is_match = menu_matches(menus[i], value);
            $(this).toggle(is_match);
        });
    });
});
