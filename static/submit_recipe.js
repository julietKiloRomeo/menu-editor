$(document).ready(function () {
    
    $(".update").click(function(){
        var ingredients = $('table > tbody  > tr').map(row_data).toArray();
        var formData = {
          name: $("#nameinput").val(),
          placement: $("#placementinput").val(),
          rating: parseInt($("#ratinginput").val()),
          ingredients: ingredients,
        };
        
        console.log(ingredients);
        
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

	$(document).on("click", ".delete", function(){
        $(this).parents("tr").remove();
		$(".add-new").removeAttr("disabled");
    });

    
    function row_html(ingredient, amount, unit) {
        return '<tr>' +
            '<td><input type="text" class="form-control" name="ingredient" value="'+ingredient+'"></td>' +
            '<td><input type="number" class="form-control" name="amount" value='+amount+'></td>' +
            '<td><input type="text" class="form-control" name="unit" value="'+unit+'"></td>' +
			'<td><a class="delete"><i class="material-icons">&#xE872;</i></a></td>' +
        '</tr>';
    }

    function row_data(i, tr) {
        return {
          ingredient : $(tr).find('input[name="ingredient"]').val(),
          amount : parseFloat($(tr).find('input[name="amount"]').val()),
          unit : $(tr).find('input[name="unit"]').val(),
        }
    }

    
    $(".add-new").click(function(){
        var row = row_html("", 0, "");
    	$("table > tbody").append(row);
    });    
    
    recipe.ingredients.forEach(ingredient => {
        console.log(ingredient);
        var row = row_html(ingredient.ingredient, ingredient.amount, ingredient.unit);
    	$("table > tbody").append(row);        
    });
    
    
});
