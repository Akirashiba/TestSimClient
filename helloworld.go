package main

import (
    "fmt"
    // "time"
    io "io/ioutil"
    json "encoding/json"
    "net/http"
    "strings"
    "os"
    "strconv"
    //"bytes"
    "net/url"
)

const MAX_ROUTINE int = 20
const BASE_URL string = "http://198.2.196.225:80/"
const LOGIN_ENDPOINT string = "api/v1/user/scan-login/"
const ORDER_ENDPOINT string = "api/v1/order/new/"
const CHECK_ENDPOINT string = "api/v1/play/content/"
const USER_FILE string = "user_info.json"

// func createOrder(){
//     fmt.Println(1)
// }

func UserInfoSave(data []byte){
    fp, err := os.OpenFile(USER_FILE, os.O_RDWR|os.O_CREATE, 0755)
    if err != nil {
        fmt.Println(err)
    }
    defer fp.Close()
    _, err = fp.Write(data)
    if err != nil {
        fmt.Println(err)
    }
}

func UserLogin(username string, info UserInfo){
    fmt.Println("UserLogin")

    login_url := BASE_URL + LOGIN_ENDPOINT

    post_data := url.Values{"login_token": {info.Login_token},
                            "password": {info.Password},
                            "client_id": {"3"}}
    req, err := http.NewRequest("POST", login_url, strings.NewReader(post_data.Encode()))
    req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

    fmt.Println(req)
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        fmt.Println("UserLogin Error")
    }
    defer resp.Body.Close()

    statuscode := resp.StatusCode
    fmt.Println(statuscode)
    
    if statuscode == 200{
        var result map[string]interface{}
        json.NewDecoder(resp.Body).Decode(&result)
        info.Token = result["token"].(string)
    }
}

func CheckAlive(token string) bool {
    fmt.Println("CheckAlive")
    check_url := BASE_URL + CHECK_ENDPOINT
    token = "Galaxy " + token

    req, err := http.NewRequest("POST", check_url, strings.NewReader("play_id=1"))
    req.Header.Set("Authorization", token)
    req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        fmt.Println("CheckAlive Error")
    }
    defer resp.Body.Close()

    statuscode := resp.StatusCode
    
    if statuscode == 200{
        return true
    }else{
        return false
    }
    
}

type UserInfo struct {
    Login_token string
    Password string
    Token string
}

func GetUserInfo() map[string]UserInfo {
    data, err := io.ReadFile(USER_FILE)
    if err != nil{
        fmt.Println(err)
    }

    datajson := []byte(data)
    var user_info map[string]UserInfo

    err = json.Unmarshal(datajson, &user_info)
    if err != nil{
        fmt.Println(err)
    }

    fmt.Println(user_info)

    return user_info
}

func main(){
    user_info := GetUserInfo()

    //var users [MAX_ROUTINE]UserInfo
    for i:=0; i<MAX_ROUTINE; i++ {
        username := "SimName" + strconv.Itoa(i)
        info := user_info[username]
        if info.Token != "" {
            is_alive := CheckAlive(info.Token)
            if !is_alive {
                UserLogin(username ,info)
            }
        }else{
            UserLogin(username ,info)
        }
    }
    marshal_info, err := json.Marshal(user_info)
    if err != nil{
        fmt.Println(err)
    }
    UserInfoSave(marshal_info)

}