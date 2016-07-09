FROM golang

# Copy the local package files to the container's workspace.
ADD *.go /go/src/gentoo-stable

# Build the outyet command inside the container.
# (You may fetch or manage dependencies here,
# either manually or with a tool like "godep".)
RUN mkdir -p /shared/data /shared/logs; \
    echo "[]" > /shared/data/database; \
    echo "[]" > /shared/data/priority; \
    echo "{}" > /shared/data/unstable; \
    echo "{}" > /shared/data/stable; \
    go get github.com/gorilla/mux; \
    go get github.com/jmcvetta/napping; \
    go get github.com/tj/go-dropbox; \
    go install gentoo-stable

# Run the outyet command by default when the container starts.
CMD /go/bin/gentoo-stable

# Document that the service listens on port 8080.
EXPOSE 8080
