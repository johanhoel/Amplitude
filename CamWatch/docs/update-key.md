# How to make the secret key for CamWatch updates

CamWatch wants to look at your code on GitHub.
Your code is private, like a locked diary.
You make a special key.
The key lets CamWatch read the code.
It can never change the code.

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
   Click outside the list to close it.
6. **Contents** now shows with a small menu next to it.
   Make sure the menu says **Read-only**.
   If it says **Read and write**, click it and choose **Read-only**.
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

Look at **Updates** again.
You see one of two messages:

- **✓ Up to date**: it works.
  CamWatch has the newest version.
- **● New version** with an **Update now** button: it works too.
  Press the button when you want the new version.

You see **GitHub refused**?
Then something went wrong with the key.
Make a new key and check steps 4, 5 and 6 carefully.

## Two rules for secret keys

1. Never show the key to anyone.
   Do not send it in a message or put it in a photo.
2. You can close the GitHub page now.
   CamWatch keeps the key safe and never shows it again.
