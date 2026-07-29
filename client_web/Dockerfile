FROM docker.io/library/nginx:alpine

# Copy static files to Nginx's default public directory
COPY . /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Nginx starts automatically with the default CMD