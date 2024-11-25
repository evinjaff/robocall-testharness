# blogs

A static site generator I built to publish blog posts written in markdown about personal projects to GitHub pages. Makes use of markdown to write posts, pandoc, and some light templating.

### Requirements

- A UNIX-like terminal
- Pandoc installed as a CLI that can convert between markdown and html
- Python 3.5 or higher (because subprocess library used)

### How to Run/Deploy

#### Preview rendered site

If you want to preview what the site will look like when rendered, invoke python to run the rederer:

``` 
python3 render.py
```

This will render the blog and all posts in the `posts/` directory to a which will be available for preview by default in the `output/` folder. If you are hosting your blog not using <a href="https://pages.github.com/">GitHub pages</a>, you can serve the `output/` folder on as your blog. If you need to edit any parameters, `config.py`


#### Publish to GitHub Pages

~~Run publish.sh from the command line and it will be responsible for rendering, committing, and pushing to the appropriate branches.~~

GitHub pages publishing is now completely automated. You will need to tweak some of the lines in `.github/workflows/main.yml` to adjust for your own github, but once this is done any push to the master branch will run a GitHub action to publish your draft post. **Do NOT commit the output/ folder to main, just commit the updated posts/ folder since the GitHub Actions VM will render the blog for you.** For the convenience of the user, I've included the `output/` folder in the gitignore so this doesn't happen but sometimes git is stubborn.