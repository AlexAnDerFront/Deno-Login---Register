import { Application } from "jsr:@oak/oak/application";
import { Router } from "jsr:@oak/oak/router";
import { home, login, register, protectedRoute, postLogin, postRegister, logout } from "./routes.ts"
import  userMiddleware  from "./userMiddleware.ts"

const app = new Application();
const router = new Router();            

app.use(userMiddleware)

router
    .get("/", home)
    .get("/login", login)
    .get("/register", register)
    .get("/protectedRoute", protectedRoute)
    .post("/login", postLogin)
    .post("/register", postRegister)
    .get('/logout', logout)
    ;
app.use(router.routes());
app.use(router.allowedMethods());

app.addEventListener('error', evt => {
    console.log(evt.error)
})
app.listen({ port: 8080 });
console.log("Server running on http://localhost:8080/");