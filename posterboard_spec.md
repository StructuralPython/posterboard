# Socials portal

## Scope
- A portal where I can write linkedin posts (with picture, videos, or carouse content) without having to be on LinkedIn.
- The tool will be hosted on a bunny.net magic container
- The tool will allow the user to login to activate the API key
- The tools will keep track of the date and how many days left until the key needs to be renewed
- The database will be a sqlite database
- Caddy will be the reverse proxy
- Authentication will be via tinyauth
- The container will have rclone installed and will backup the sqlite file every 5 minutes to a bunny.net storage space.
- The url will eventually be posterboard.structuralpython.com

## Features
- Posts can be written in markdown using bold, italic, and code. Markdown parser (custom Wenmode renderer) converts to unicode italic, bold, and monospace characters (where possible).
- LinkedIn has the ability to schedule posts in advance however we will not be using that feature. We will only be using the immediate post API. The tool (posterboard) will take care of the scheduling internally. This will create two lists of posts: posts scheduled and previous posts. Scheduled posts can be edited until the post date, old posts are immutable. 
- The post editing page will produce a live preview of the post (simulated within the posterboard tool). The preview will have a collapsed and estimated "un-collapsed" view of the post.
