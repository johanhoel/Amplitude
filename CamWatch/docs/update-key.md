# How to make the secret key for CamWatch (optional)

> ✅ You do not need this key for updates.
> The CamWatch code on GitHub is public, so CamWatch reads it without a key.

The key does two extra things:

- CamWatch sends feature requests to GitHub by itself.
  Without the key, GitHub opens with your request filled in, and you press Submit.
- GitHub allows more update checks per hour.

Only the owner of the GitHub repository can make this key.
A repository that is private again always needs the key.

Do you have a key already?
Then open it on <https://github.com/settings/personal-access-tokens> and click **Edit**.
Do steps 5 and 6.
The key stays the same, so CamWatch needs nothing new.

CamWatch shows this guide too: **Settings → Updates → Where updates come from → How to make the key, step by step**.

## Part 1: Make the key on GitHub

1. Open this page: <https://github.com/settings/personal-access-tokens/new>.
   If GitHub asks you to log in, log in.
2. Find the box **Token name**.
   Type `CamWatch updates`.
3. Find **Expiration**.
   Pick **Custom** and choose a date one year from today.
   The key stops working on that date.
   Then you make a new key.
4. Find **Repository access**.
   Click **Only select repositories**.
   Click **Amplitude** in the list.
5. Find **Permissions** and click **Add permissions**.
   Type `contents` in the search box.
   Tick **Contents**.
   Then type `issues` and tick **Issues**.
   Click outside the list to close it.
6. **Contents** and **Issues** now show, each with a small menu next to it.
   Set **Contents** to **Read-only**: CamWatch only reads the code.
   Set **Issues** to **Read and write**: CamWatch sends your feature requests there.
   GitHub can add **Metadata** by itself.
   Leave it there.
7. Scroll to the bottom.
   Click the green **Generate token** button.
   If GitHub asks again, click **Generate token** again.
8. GitHub shows your key.
   It is a long line that starts with `github_pat_`.
   Click the small copy button next to it.

> ⚠️ GitHub shows the key only once.
> Keep this page open until you finish Part 2.

Can't find **Contents**? Check step 4.
GitHub shows the full list only after you pick a repository.

## Part 2: Give the key to CamWatch

9. Open CamWatch and go to **Settings → Updates**.
   Production: <http://192.168.1.81:8080/settings#updates>
10. Click **Where updates come from**.
    A small box opens.
11. Click in the box **Access key**.
    Paste the key: press **Ctrl** and **V** together.
12. Click **Save and check**.

## Part 3: Check that it works

Open **Request a feature** at the bottom of any CamWatch page.
The page no longer says that GitHub opens for you.
That means CamWatch sends requests by itself now.

A request says **GitHub refused**?
Then something went wrong with the key.
Make a new key and check steps 4, 5 and 6 carefully.

## Two rules for secret keys

1. Never show the key to anyone.
   Do not send it in a message or put it in a photo.
2. You can close the GitHub page now.
   CamWatch keeps the key safe and never shows it again.
