// const API_HOST = IS_DRAFTOUT ? "https://mcsr-ranked-distance-api.ruslan.page/draftout" : "https://mcsr-ranked-distance-api.ruslan.page/mcsr-ranked"
const API_HOST = IS_DRAFTOUT ? "http://127.0.0.1:8882" : "http://127.0.0.1:8881";

function makeMatchInfoUrlMcsrRanked(match) {
    return `https://mcsrranked.com/stats/${match.player1}/vs/${match.player2}/${match.id}?season=${match.season}`;
}

function makeMatchInfoUrlDraftout(match) {
    return `https://draftoutmc.com/leaderboard/${match.player1}/${match.id}`;
}

const makeMatchInfoUrl = IS_DRAFTOUT ? makeMatchInfoUrlDraftout : makeMatchInfoUrlMcsrRanked;

const player1_field = document.getElementById("player1");
const player2_field = document.getElementById("player2");
const form = document.getElementById("get-distance-form");
const error_alert = document.getElementById("alert-error");
const info_alert = document.getElementById("alert-info");
const submit_btn = document.getElementById("get-distance-btn");

function showError(text) {
    info_alert.classList.add("d-none");
    error_alert.classList.remove("d-none");
    error_alert.classList.add("d-flex");
    error_alert.innerHTML = "";

    const span = document.createElement("span");
    span.innerText = text;
    error_alert.append(span);
}

function showInfo(text, withSpinner = false) {
    error_alert.classList.add("d-none");
    info_alert.classList.remove("d-none");
    info_alert.classList.add("d-flex");
    info_alert.innerHTML = "";

    if (withSpinner) {
        const spinner = document.createElement("div");
        spinner.className = "spinner-border";
        spinner.role = "status";
        info_alert.appendChild(spinner);
    }

    const span = document.createElement("span");
    span.innerText = text;
    info_alert.append(span);
}

form.addEventListener("submit", (event) => {
    event.preventDefault();

    const player1_name = player1_field.value;
    const player2_name = player2_field.value;

    const url = new URL(location);
    url.searchParams.set("player1", player1_name);
    url.searchParams.set("player2", player2_name);
    history.pushState({}, "", url);

    showInfo("Loading, please wait...", true);
    submit_btn.disabled = "disabled";

    fetch(`${API_HOST}/distance/${player1_name}/${player2_name}`)
        .then((resp) => {
            submit_btn.disabled = "";

            if (!resp.ok) {
                showError("Failed to fetch info: server error");
                return;
            }

            resp.json()
                .then((json) => {
                    if (!Array.isArray(json.matches)) {
                        showError("Failed to fetch info: got invalid json from server");
                        return;
                    }

                    showInfo("");
                    info_alert.innerHTML = "";

                    const result_container = document.createElement("div");
                    result_container.classList = "d-flex flex-column gap-1 w-100";
                    info_alert.appendChild(result_container);

                    const title = document.createElement("h4");
                    result_container.appendChild(title);

                    const player1_bold = document.createElement("b");
                    player1_bold.innerText = player1_name;
                    const player2_bold = document.createElement("b");
                    player2_bold.innerText = player2_name;

                    if (json.matches.length === 0) {
                        title.append("Didn't find any match \"chain\" between ", player1_bold, " and ", player2_bold);
                    } else {
                        const matches_count_bold = document.createElement("b");
                        matches_count_bold.innerText = String(json.matches.length);
                        if (json.matches.length === 1)
                            title.append(player1_bold, " has actually played directly against ", player2_bold, " at some point");
                        else
                            title.append(player1_bold, " is ", matches_count_bold, " matches away from ", player2_bold);

                        const matches_title = document.createElement("p");
                        if (json.matches.length === 1)
                            matches_title.innerText = `Here's that match:`;
                        else
                            matches_title.innerText = `Here're all the matches:`;
                        result_container.appendChild(matches_title);

                        const matches_list = document.createElement("ul");
                        matches_list.classList = "list-group w-100 fs-5";
                        result_container.appendChild(matches_list);

                        let item_num = 1;
                        for (const match of json.matches) {
                            const match_item = document.createElement("li");
                            match_item.classList.add("list-group-item");
                            matches_list.appendChild(match_item);

                            const match_with_url = document.createElement("a");
                            match_with_url.href = makeMatchInfoUrl(match);
                            match_with_url.innerText = `${match.player1} vs ${match.player2}`;
                            match_item.append(`${item_num++}. `, match_with_url);
                            if (!IS_DRAFTOUT)
                                match_item.append(` (in season ${match.season})`);
                        }
                    }

                    if (json.additional_info) {
                        const matches_title = document.createElement("p");
                        matches_title.innerText = json.additional_info;
                        result_container.appendChild(matches_title);
                    }
                }, () => {
                    showError("Failed to fetch info: got invalid response from server");
                });
        }, () => {
            submit_btn.disabled = "";
            showError("Failed to fetch info: server connection error");
        });
});

function fillFromQuerystring() {
    const url_params = new URLSearchParams(window.location.search);
    const player1_name = url_params.get("player1");
    const player2_name = url_params.get("player2");
    if (player1_name)
        player1_field.value = player1_name;
    if (player2_name)
        player2_field.value = player2_name;

    if (player1_name && player2_name)
        form.requestSubmit();
}

fillFromQuerystring();