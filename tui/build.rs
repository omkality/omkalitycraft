fn main() {
    println!("cargo:rerun-if-changed=windows.rc");
    println!("cargo:rerun-if-changed=assets/eden-ore.ico");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        embed_resource::compile_for("windows.rc", ["omk-tui"], embed_resource::NONE)
            .manifest_required()
            .expect("Failed to embed the Eden ore icon");
    }
}
