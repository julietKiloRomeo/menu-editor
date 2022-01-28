$(document).ready(function () {
    $(".update").click(function () {
        var recipes = $("table > tbody > tr").toArray().map(row_data);
        console.log(recipes);
        
        var formData = {
            name: $("#nameinput").val(),
            rating: parseInt($("#ratinginput").val()),
            recipes: recipes,
        };
        
        package = {
            type: "POST",
            url: url,
            data: JSON.stringify(formData),
            dataType: "json",
            contentType: "application/json",
        };

        $.ajax(package).done(function (data) {
            console.log(data);
        });
        
        
        
    });
    $(".delete").click(function () {
        console.log(JSON.stringify({"doc_id": doc_id}))
        package = {
            type: "POST",
            url: "/api/menu/delete",
            data: JSON.stringify({"doc_id": doc_id}),
            dataType: "json",
            contentType: "application/json",
        };
        $.ajax(package).done(function (data) {
            window.location.href = "/menu";
        });
    });
    
    $(document).on("click", ".delete", function () {
        $(this).parents("tr").remove();
        $(".add-new").removeAttr("disabled");
    });

    function row_html(recipe) {
        return (
            "<tr>" +
            '<td><input type="text" class="form-control" name="recipe" value="' +
            recipe.recipe.ingredient +
            '"></td>' +
            '<td><input type="text" class="form-control" name="amount" value="' +
            recipe.recipe.amount +
            '"></td>' +
            '<td><input type="text" class="form-control" name="unit" value="' +
            recipe.recipe.unit +
            '"></td>' +
            '<td>'+
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="mon" value="mon">' +
            '  <label class="form-check-label" for="mon">mon</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="tue" value="tue">' +
            '  <label class="form-check-label" for="tue">tue</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="wed" value="wed">' +
            '  <label class="form-check-label" for="wed">wed</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="thu" value="thu">' +
            '  <label class="form-check-label" for="thu">thu</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="fri" value="fri">' +
            '  <label class="form-check-label" for="fri">fri</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="sat" value="sat">' +
            '  <label class="form-check-label" for="sat">sat</label>' +
            '</div>' +
            '<div class="form-check form-check-inline">' +
            '  <input class="form-check-input" type="checkbox" id="sun" value="sun">' +
            '  <label class="form-check-label" for="sun">sun</label>' +
            '</div>' +
            '</td>' +
            '<td><a class="delete"><i class="material-icons">&#xE872;</i></a></td>' +
            "</tr>"
        );
    }

    function row_data(tr) {
        //console.log(i)
        var days = $(tr).find('.form-check-input:checked').toArray().map(el => $(el).val());
        return {
            "recipe":{
                ingredient: $(tr).find('input[name="recipe"]').val(),
                amount: parseFloat($(tr).find('input[name="amount"]').val()),
                unit: $(tr).find('input[name="unit"]').val(),
            },
            "day": days,
        };
    }

    $(".add-new").click(function () {
        var recipe = {"recipe":{"ingredient":"", "amount":0, "unit":""}}
        var row = row_html(recipe);
        $("table > tbody").append(row);
    });

    menu.recipes.forEach( recipe => {
        var row = $(row_html(recipe));
        console.log(row)
        row.appendTo("table > tbody");
        recipe.day.forEach(day => row.find("#"+day).prop( "checked", true ))
        
    });
    

    
});
