CEAP E-Voting System - deploy notes
1. Upload the CONTENTS of this folder to the ROOT of your GitHub repo
   (app.py, requirements.txt, render.yaml must be on the repo's first page).
2. In Render > your service > Environment, set:
     DEMO_MODE      = 0
     BREVO_API_KEY  = (API key from Brevo)
     MAIL_SENDER    = (the sender email you verified in Brevo)
     ADMIN_PASSWORD = (a strong password of your choice)
3. Deploy. Admin username is: admin
NOTE: on Render's free plan the database resets on every redeploy.
Keep a CSV of your voters so you can re-upload it via Manage Voters.
