package main

import (
	"crypto/hmac"
	"crypto/sha1"
	"encoding/hex"
	"io/ioutil"
	"strconv"
	"strings"
	"time"
)

func get_swift_account() string {
	return "AUTH_3f494a0f16624739bafc9a4819870992"
}

func sign(expires int, method, container_name, object_name, secret string) string {
	url := "/v1/" + get_swift_account() + "/" + container_name + "/" + object_name
	mac := hmac.New(sha1.New, []byte(secret))
	str := strings.Join([]string{method, strconv.Itoa(expires), url}, "\n")
	mac.Write([]byte(str))
	sig := hex.EncodeToString(mac.Sum(nil))
	return url + "?temp_url_sig=" + sig + "&temp_url_expires=" + strconv.Itoa(expires)
}

func sign_urls(secret string) string {
	duration := 600
	container := "LogBackup"
	now := int(time.Now().Unix())
	base_object := strconv.Itoa(now)
	expires := int(now + duration)
	url := sign(expires, "PUT", container, base_object, secret)
	return url
}
func get_temp_url() string {
	dat, err := ioutil.ReadFile("/secret/secret")
	check(err)
	secret := strings.TrimSpace(string(dat))
	return "https://swift-yyc.cloud.cybera.ca:8080" + (sign_urls(secret))
}
