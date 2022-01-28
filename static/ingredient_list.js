$(document).ready(function () {
    $(".update").click(function () {
        var visible_parsed_ingredients = $("table > tbody  > tr:visible")
            .map(row_data)
            .toArray();

        update_package = {
            type: "POST",
            url: "/api/ingredient",
            data: JSON.stringify(visible_parsed_ingredients),
            dataType: "json",
            contentType: "application/json",
        };

        $.ajax(update_package).done(function (data) {
            console.log(data);
        });

        delete_package = {
            type: "POST",
            url: "/api/ingredient/delete",
            data: JSON.stringify(deleted_ingredients),
            dataType: "json",
            contentType: "application/json",
        };

        if (deleted_ingredients.length) {
            $.ajax(delete_package).done(function (data) {
                console.log(data);
            });
        }
    });

    $(document).on("click", ".delete", function () {
        var id = row_data(0, $(this).parents("tr"))["doc_id"];
        deleted_ingredients.push(id);
        $(this).parents("tr").remove();
        $(".add-new").removeAttr("disabled");
    });

    function row_html(doc_id, ingredient, amount, unit) {
        return (
            "<tr>" +
            '<input type="hidden" name="doc_id" value="' +
            doc_id +
            '">' +
            '<td><input type="text" class="form-control" name="name" value="' +
            ingredient +
            '"></td>' +
            "<td>" +
            categories_select +
            "</td>" +
            '<td><input type="text" class="form-control" name="alii" value="' +
            unit +
            '"></td>' +
            '<td><a class="delete"><i class="material-icons">&#xE872;</i></a></td>' +
            "</tr>"
        );
    }

    function row_data(i, tr) {
        return {
            doc_id: parseInt($(tr).find('input[name="doc_id"]').val()) || -1,
            name: $(tr).find('input[name="name"]').val(),
            category: $(tr).find('select[name="category"]').val(),
            alii: $(tr)
                .find('input[name="alii"]')
                .val()
                .split(",")
                .map((s) => s.trim()),
        };
    }

    $(".add-new").click(function () {
        var row = row_html("", "none", []);
        $("table > tbody").append(row);
    });

    ingredients.forEach((ingredient) => {
        var row = $(
            row_html(
                ingredient.doc_id,
                ingredient.name,
                ingredient.category,
                ingredient.alii
            )
        );
        row.appendTo("table > tbody");
        row.find('select[name="category"]').val(ingredient.category).change();
    });

    const recipe_matches = function (recipe, query) {
        let str_matches = (name) => name.toLowerCase().indexOf(query) > -1;

        name_matches = str_matches(recipe.name);
        ingredient_matches = recipe.ingredients
            .map((l) => l.ingredient)
            .some(str_matches);

        return name_matches || ingredient_matches;
    };

    $("#namesearchbox").on("keyup", function () {
        var query = $(this).val().toLowerCase();

        $("table > tbody > tr").filter(function (i, e) {
            var name = $(e).find('input[name="name"]').val();
            var is_match = name.toLowerCase().indexOf(query) > -1;
            $(this).toggle(is_match);
        });
    });

    $("#categoryfilter").change(function () {
        var query = $(this).val();
        $("table > tbody > tr").filter(function (i, e) {
            var cat = $(e).find('select[name="category"]').val();
            var is_match = query === cat || query === "--";
            $(this).toggle(is_match);
        });
    });
});
