// get btc,eth,ltc price using coinmarketcap.com api
$(function () {
    var url = "https://api.coinmarketcap.com/v1/ticker/?limit=20";
    $.get(url, function (data) {
        $("#loading_market").hide();
        for(i in data){
            if (data[i]["id"]=="bitcoin"){
                $("#loading_bitcoin").hide();
                $("#bitcoin").text("$" + data[i]["price_usd"]);
            }
            if (data[i]["id"]=="ethereum"){
                $("#loading_ethereum").hide();
                $("#ethereum").text("$" + data[i]["price_usd"]);
            }
            if (data[i]["id"]=="litecoin"){
                $("#loading_litecoin").hide();
                $("#litecoin").text("$" + data[i]["price_usd"]);
            }
            $("tbody").append(
                `<tr><td>${data[i]['rank']}</td><td>${data[i]['name']}</td><td>${data[i]['symbol']}</td><td>$ ${data[i]['price_usd']}</td><td>$ ${data[i]['24h_volume_usd']}</td><td>${data[i]['percent_change_24h']}%</td><tr>`
            )

        }

    });

});