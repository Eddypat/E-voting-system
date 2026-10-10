document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", function (e) {
            const matric = document.getElementById("matric_no").value.trim();
            const pattern = /^[A-Za-z]{4}\/[A-Za-z]-[A-Za-z]{3}\/\d{4}\/\d{3,5}$/;
            if (!pattern.test(matric)) {
                e.preventDefault();
                alert("Please enter a valid matriculation number, e.g. CEAP/N-COM/2024/3226");
            }
        });
    }
    const otpInput = document.getElementById("otp");
    if (otpInput) {
        otpInput.addEventListener("input", function () {
            this.value = this.value.replace(/\D/g, "").slice(0, 6);
        });
    }
    const ballotForm = document.getElementById("ballotForm");
    if (ballotForm) {
        ballotForm.addEventListener("submit", function (e) {
            const fieldsets = ballotForm.querySelectorAll("fieldset.position-block");
            let missing = [];
            fieldsets.forEach(function (fs) {
                const checked = fs.querySelector("input[type=radio]:checked");
                if (!checked) {
                    missing.push(fs.querySelector("legend").textContent);
                }
            });
            if (missing.length > 0) {
                e.preventDefault();
                alert("Please select a candidate for: " + missing.join(", "));
            } else {
                const confirmed = confirm("Submit your ballot? This action cannot be undone.");
                if (!confirmed) e.preventDefault();
            }
        });
    }
});
